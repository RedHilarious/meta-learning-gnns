import time
from copy import deepcopy
from statistics import mean, stdev

import torch.nn.functional as func
from torch import optim
from torchmetrics import F1
from tqdm.auto import tqdm

from models.GraphTrainer import GraphTrainer
from models.gat_encoder_sparse_pushkar import GatNet
from models.proto_net import ProtoNet
from models.train_utils import *
from samplers.batch_sampler import split_list


class ProtoMAML(GraphTrainer):

    # noinspection PyUnusedLocal
    def __init__(self, model_params, opt_hparams, label_names, batch_size):
        """
        Inputs
            lr - Learning rate of the outer loop Adam optimizer
            lr_inner - Learning rate of the inner loop SGD optimizer
            lr_output - Learning rate for the output layer in the inner loop
            n_inner_updates - Number of inner loop updates to perform
        """
        super().__init__(n_classes=model_params['output_dim'])
        self.save_hyperparameters()

        self.n_inner_updates = model_params['n_inner_updates']

        flipped_weights = torch.flip(model_params["class_weight"], dims=[0])
        # pos_weight = flipped_weights
        self.loss_module = torch.nn.BCEWithLogitsLoss()

        self.model = GatNet(model_params)

    def configure_optimizers(self):
        optimizer = optim.AdamW(self.parameters(), lr=self.hparams.opt_hparams['lr'])
        scheduler = optim.lr_scheduler.MultiStepLR(optimizer, milestones=[140, 180], gamma=0.1)
        return [optimizer], [scheduler]

    def adapt_few_shot(self, support_graphs, support_targets, mode):

        x, edge_index, cl_mask = get_subgraph_batch(support_graphs)

        # Determine prototype initialization
        support_feats = self.model(x, edge_index, mode).squeeze()
        support_feats = support_feats[cl_mask]

        prototypes, classes = ProtoNet.calculate_prototypes(support_feats, support_targets)

        # Copy model for inner-loop model and optimizer
        local_model = deepcopy(self.model)
        local_model.train()
        local_optim = optim.SGD(local_model.parameters(), lr=self.hparams.opt_hparams['lr_inner'])
        local_optim.zero_grad()

        # Create output layer weights with prototype-based initialization
        init_weight = 2 * prototypes
        init_bias = -torch.norm(prototypes, dim=1) ** 2
        output_weight = init_weight.detach().requires_grad_()
        output_bias = init_bias.detach().requires_grad_()

        # Optimize inner loop model on support set
        for _ in range(self.n_inner_updates):
            # Determine loss on the support set
            loss, predictions = run_model(local_model, output_weight, output_bias, support_graphs, support_targets,
                                          mode, self.loss_module)

            # Calculate gradients and perform inner loop update
            loss.backward()
            local_optim.step()

            # Update output layer via SGD
            output_weight.data -= self.hparams.opt_hparams['lr_output'] * output_weight.grad
            output_bias.data -= self.hparams.opt_hparams['lr_output'] * output_bias.grad

            # Reset gradients
            local_optim.zero_grad()
            output_weight.grad.fill_(0)
            output_bias.grad.fill_(0)

        # Re-attach computation graph of prototypes
        output_weight = (output_weight - init_weight).detach() + init_weight
        output_bias = (output_bias - init_bias).detach() + init_bias

        return local_model, output_weight, output_bias, classes

    # @staticmethod
    # def get_labels(classes, targets):
    #     # noinspection PyUnresolvedReferences
    #     return (classes[None, :] == targets[:, None]).long().argmax(dim=-1)

    def outer_loop(self, batch, mode="train"):
        losses = []

        self.model.zero_grad()

        # Determine gradients for batch of tasks
        for task_batch in batch:

            graphs, targets = task_batch
            support_graphs, query_graphs = split_list(graphs)
            support_targets, query_targets = split_list(targets)

            # Perform inner loop adaptation
            local_model, output_weight, output_bias, classes = self.adapt_few_shot(support_graphs, support_targets,
                                                                                   mode)

            # Determine loss of query set
            loss, predictions = run_model(local_model, output_weight, output_bias, query_graphs, query_targets, mode,
                                          self.loss_module)

            pred = predictions.argmax(dim=-1)
            for mode_dict, _ in self.metrics.values():
                mode_dict[mode].update(pred, query_targets)

            # Calculate gradients for query set loss
            if mode == "train":
                loss.backward()

                # print("Model parameters.")
                count = 0
                for i, (p_global, p_local) in enumerate(zip(self.model.parameters(), local_model.parameters())):
                    if p_global.grad is None or p_local.grad is None:
                        # print(f"Grad none at position: {i}")
                        count += 1
                    else:
                        # First-order approx. -> add gradients of fine-tuned and base model
                        p_global.grad += p_local.grad

                # print(f"Grads None: {count}")

            losses.append(loss.detach())

        # Perform update of base model
        if mode == "train":
            opt = self.optimizers()
            opt.step()
            # noinspection PyUnresolvedReferences
            opt.zero_grad()

        self.log_on_epoch(f"{mode}/loss", sum(losses) / len(losses))

    def training_step(self, batch, batch_idx):
        self.outer_loop(batch, mode="train")

        # Returning None means skipping the default training optimizer steps by PyTorch Lightning
        return None

    def validation_step(self, batch, batch_idx):
        # Validation requires to finetune a model, hence we need to enable gradients
        torch.set_grad_enabled(True)
        self.outer_loop(batch, mode="val")
        torch.set_grad_enabled(False)


def run_model(local_model, output_weight, output_bias, graphs, targets, mode, loss_module=None):
    """
    Execute a model with given output layer weights and inputs.
    """

    x, edge_index, cl_mask = get_subgraph_batch(graphs)
    logits = local_model(x, edge_index, mode).squeeze()
    logits = logits[cl_mask]

    logits = func.linear(logits, output_weight, output_bias)

    # if we only have one class anyway, no one-hot required
    targets = func.one_hot(targets) if logits.shape[1] == 2 else targets.unsqueeze(dim=1)

    # loss = func.cross_entropy(predictions, targets)
    loss = loss_module(logits, targets.float()) if loss_module is not None else None

    return loss, logits


def test_protomaml(model, test_loader, num_classes):
    mode = 'test'
    model = model.to(DEVICE)
    model.eval()

    # TODO: use inner loop updates of 200 --> should be higher than in training

    test_start = time.time()

    # Iterate through the full dataset in two manners:
    # First, to select the k-shot batch. Second, to evaluate the model on all other batches.

    f1_macros, f1_fakes, f1_reals = [], [], []

    for support_batch_idx, batch in tqdm(enumerate(test_loader), "\nPerforming few-shot fine tuning in testing"):
        support_graphs, _, support_targets, _ = batch

        # graphs are automatically put to device in adapt few shot
        support_targets = support_targets.to(DEVICE)

        # Finetune new model on support set
        local_model, output_weight, output_bias, classes = model.adapt_few_shot(support_graphs, support_targets, mode)

        f1 = F1(num_classes=num_classes, average='none').to(DEVICE)
        f1_macro = F1(num_classes=num_classes, average='macro').to(DEVICE)

        with torch.no_grad():  # No gradients for query set needed
            local_model.eval()

            # Evaluate all examples in test dataset
            for query_batch_idx, test_batch in enumerate(test_loader):

                if support_batch_idx == query_batch_idx:
                    # Exclude support set elements
                    continue

                support_graphs, query_graphs, support_targets, query_targets = batch
                graphs = support_graphs + query_graphs
                targets = torch.cat([support_targets, query_targets]).to(DEVICE)

                _, predictions = run_model(local_model, output_weight, output_bias, graphs, targets, mode)

                pred = predictions.argmax(dim=-1)
                f1.update(pred, targets)
                f1_macro.update(pred, targets)

            f1_macros.append(f1_macro.compute().item())
            f1_1, f1_2 = f1.compute()
            f1_reals.append(f1_2.item())
            f1_fakes.append(f1_1.item())

    test_end = time.time()
    test_elapsed = test_end - test_start

    return (mean(f1_fakes), stdev(f1_fakes)), (mean(f1_reals), stdev(f1_reals)), \
           (mean(f1_macros), stdev(f1_macros)), test_elapsed

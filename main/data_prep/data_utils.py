import torch.cuda

from data_prep.graph_dataset import DGLSubGraphs, DglGraphDataset, collate_fn_proto, collate_fn_base
from models.batch_sampler import FewShotSubgraphSampler

SUPPORTED_DATASETS = ['gossipcop', 'twitterHateSpeech']


def get_data(data_train, data_eval, model, hop_size, top_k, k_shot, nr_train_docs, feature_type, vocab_size, dirs):
    """
    Creates and returns the correct data object depending on data_name.
    Args:
        data_train (str): Name of the data corpus which should be used for training.
        data_eval (str): Name of the data corpus which should be used for testing/evaluation.
        model (str): Name of the model should be used.
        hop_size (int): Number of hops used to create sub graphs.
        top_k (int): Number of top users to be used in graph.
        k_shot (int): Number of examples used per task/batch.
        nr_train_docs (str): Number of total documents used for test/train/val.
        feature_type (int): Type of features that should be used.
        vocab_size (int): Size of the vocabulary.
        dirs (str): Path to the data (full & complete) to be used to create the graph (feature file, edge file etc.)
    Raises:
        Exception: if the data_name is not in SUPPORTED_DATASETS.
    """

    if data_train not in SUPPORTED_DATASETS or data_eval not in SUPPORTED_DATASETS:
        raise ValueError(f"Data with name '{data_train}' or '{data_eval}' is not supported.")

    graph_data_train = DglGraphDataset(data_train, top_k, feature_type, vocab_size, nr_train_docs, *dirs)

    num_workers = 6 if torch.cuda.is_available() else 0  # mac has 8 CPUs
    collate_fn = collate_fn_base if model == 'gat' else collate_fn_proto

    train_loader = get_loader(graph_data_train, model, hop_size, k_shot, num_workers, collate_fn, 'train')
    train_val_loader = get_loader(graph_data_train, model, hop_size, k_shot, num_workers, collate_fn, 'val')

    # creating a test loader from the other dataset
    graph_data_eval = DglGraphDataset(data_eval, top_k, feature_type, vocab_size, nr_train_docs, *dirs)
    test_loader = get_loader(graph_data_eval, model, hop_size, k_shot, num_workers, collate_fn, 'test')
    test_val_loader = get_loader(graph_data_eval, model, hop_size, k_shot, num_workers, collate_fn, 'val')

    assert graph_data_train.num_features == graph_data_eval.num_features, \
        "Number of features for train and eval data is not equal!"

    loaders = (train_loader, train_val_loader, test_val_loader, test_loader)
    labels = (graph_data_train.labels, graph_data_eval.labels)

    return loaders, graph_data_train.num_features, labels


def get_loader(graph_data, model, hop_size, k_shot, num_workers, collate_fn, mode):
    graphs = DGLSubGraphs(graph_data, f'{mode}_mask', h_size=hop_size, meta=model != 'gat')
    sampler = FewShotSubgraphSampler(graphs, include_query=True, k_shot=k_shot)
    print(f"\n{mode} sampler amount of batches: {sampler.num_batches}")
    return graphs.as_dataloader(sampler, num_workers, collate_fn)

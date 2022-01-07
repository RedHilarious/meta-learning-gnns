import torch
import torch.nn.functional as func
from torch import nn


class GATLayer(nn.Module):
    """
    Simple GAT layer, similar to https://arxiv.org/abs/1710.10903
    """

    def __init__(self, in_features, out_features, dropout=0.6, attn_drop=0.6, alpha=0.2, attn=True, concat=False):
        super(GATLayer, self).__init__()

        self.in_features = in_features
        self.out_features = out_features
        self.attn_dropout = nn.Dropout(attn_drop)
        self.dropout = nn.Dropout(dropout)
        self.alpha = alpha
        self.concat = concat
        self.attn = attn

        # Constant projection
        # TODO: we don't project down on sth, constant projection
        # self.linear = nn.Linear(in_features, out_features, bias=False)
        self.linear = nn.Linear(in_features, in_features, bias=False)

        # TODO: still initialize even if constant?
        gain = nn.init.calculate_gain('leaky_relu')
        # nn.init.xavier_uniform_(self.linear.weight.data, gain=gain)

        # grad of the linear layer false --> will not be learned but instead constant projection
        self.linear.requires_grad_(False)

        self.seq_transformation = nn.Conv1d(
            in_features, out_features, kernel_size=1, stride=1, bias=False
        )

        self.bias = nn.Parameter(torch.zeros(out_features), requires_grad=True)

        if self.attn:
            self.f_1 = nn.Conv1d(out_features, 1, kernel_size=1, stride=1)
            self.f_2 = nn.Conv1d(out_features, 1, kernel_size=1, stride=1)
            self.leaky_relu = nn.LeakyReLU(self.alpha)

    def forward(self, x, adj):

        seq = torch.transpose(x, 0, 1).unsqueeze(0)
        seq_fts = self.seq_transformation(seq)
        if self.attn:
            f_1 = self.f_1(seq_fts)
            f_2 = self.f_2(seq_fts)
            logits = (torch.transpose(f_1, 2, 1) + f_2).squeeze(0)
            coefs = func.softmax(self.leaky_relu(logits) + adj, dim=1)
        else:
            coefs = func.softmax(adj, dim=1)
        coefs = self.attn_dropout(coefs)
        seq_fts = self.dropout(torch.transpose(seq_fts.squeeze(0), 0, 1))
        ret = torch.mm(coefs, seq_fts) + self.bias
        return func.elu(ret) if self.concat else ret


class SparseGATLayer(GATLayer):
    """
    Sparse version GAT layer taken from the official PyTorch repository:
    https://github.com/Diego999/pyGAT/blob/similar_impl_tensorflow/layers.py
    """

    def forward(self, x, adj):

        assert x.is_sparse
        assert adj.is_sparse

        # x is assumed to be dense
        # if x is sparse: x = x * dense_weight_matrix (linear layer)

        # initialize x to be simple weight matrix
        x = torch.mm(x, self.linear.weight.t())

        # initialize self.transform in init of parent layer, e.g. nn.Linear(bias=False); dimensions fitting the features

        seq = torch.transpose(x, 0, 1).unsqueeze(0)
        seq_fts = self.seq_transformation(seq)

        edges = adj._indices()
        if self.attn:
            f_1 = self.f_1(seq_fts).squeeze()
            f_2 = self.f_2(seq_fts).squeeze()
            logits = f_1[edges[0]] + f_2[edges[1]]
            coefs = self.leaky_relu(logits).exp()  # E
        else:
            coefs = adj._values().exp()  # E
        coef_sum = torch.zeros_like(x[:, 0]).index_add_(0, edges[0], coefs).view(-1, 1)
        coefs = self.attn_dropout(coefs)
        sparse_coefs = torch.sparse_coo_tensor(edges, coefs)
        seq_fts = self.dropout(torch.transpose(seq_fts.squeeze(0), 0, 1))
        ret = torch.sparse.mm(sparse_coefs, seq_fts).div(coef_sum) + self.bias
        return func.elu(ret) if self.concat else ret

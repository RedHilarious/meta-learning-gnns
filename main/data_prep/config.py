RAW_DIR = '../data/raw/'
TSV_DIR = '../data/tsv/'
COMPLETE_DIR = '../data/complete/'

COMPLETE_small_DIR = '../data/complete-50/'
TSV_small_DIR = '../data/tsv-50/'

CONTENT_INFO_FILE_NAME = 'docsContentInformation.tsv'

DOC_SPLITS_FILE_NAME = 'docSplits.json'
USER_SPLITS_FILE_NAME = 'userSplits.json'

USER_2_ID_FILE_NAME = 'user2id_lr_top%s_train.json'
DOC_2_ID_FILE_NAME = 'doc2id_lr_top%s_train.json'
NODE_2_ID_FILE_NAME = 'node2id_lr_top%s_train.json'
NODE_TYPE_FILE_NAME = 'node_type_lr_top%s_train.npy'

VALID_USERS = 'valid_users_top%s.json'
RESTRICTED_USERS = 'restricted_users_%s.json'

ADJACENCY_MATRIX_FILE = 'adj_matrix_lr_top%s_train'
ADJACENCY_MATRIX_FILE_NAME = f'{ADJACENCY_MATRIX_FILE}.npz'

EDGE_TYPE_FILE = 'edge_type_lr_top%s'
EDGE_TYPE_FILE_NAME = f'{EDGE_TYPE_FILE}.npz'
EDGE_INDEX_FILE_NAME = EDGE_TYPE_FILE + '_edge.npy'
EDGE_LIST_FILE_NAME = 'edge_list_top%s.json'

FEAT_MATRIX_FILE = 'feat_matrix_lr_top%s_train'
FEAT_MATRIX_FILE_NAME = f'{FEAT_MATRIX_FILE}.npz'

SPLIT_MASK_FILE_NAME = 'split_mask.json'

# TOP_50_CONSTRAINT = 'top50'
# TOP_10_CONSTRAINT = 'top10'

DOC_2_LABELS_FILE_NAME = 'doc2labels.json'
TRAIN_LABELS_FILE_NAME = 'labels_train_val.json'
ALL_LABELS_FILE_NAME = 'labels_train_val_test.json'

DGL_GRAPH_FILE = '%s.dgl'

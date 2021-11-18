import argparse
import glob
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy.sparse import load_npz

from data_prep.config import *
from data_prep.graph_io import GraphPreprocessor, LABELS
from data_preprocess_utils import save_json_file


class FakeNewsGraphPreprocessor(GraphPreprocessor):

    def __init__(self, config):
        super().__init__(config)

        self.load_doc_splits()

        # self.aggregate_user_contexts()

        # if self.only_valid_users:
        #     self.filter_valid_users()

        self.create_user_splits()
        # self.create_doc_id_dicts()
        # self.filter_contexts()
        # self.create_adj_matrix()
        # self.create_feature_matrix()
        # self.create_labels()
        # self.create_split_masks()

    def get_doc_key(self, name, name_type='dir'):
        if name_type == 'dir':
            return name.split('gossipcop-')[1].split('/')[-1]
        elif name_type == 'file':
            return name.split('.')[0]
        else:
            raise ValueError("Name type to get ID from is neither file, nor dir!")

    def aggregate_user_contexts(self):
        self.print_step("Aggregating follower/ing relations")

        docs_users = defaultdict(set)
        count = 0
        for user_context in ['tweets', 'retweets']:
            print("\nIterating over : ", user_context)

            src_dir = self.data_raw_path(self.dataset, user_context)
            if not os.path.exists(src_dir):
                raise ValueError(f'Source directory {src_dir} does not exist!')

            for root, dirs, files in os.walk(src_dir):
                for count, file in enumerate(files):
                    file_path = os.path.join(root, file)

                    # need to differentiate between how to read them because retweets are stored as JSONs in CSV!
                    if user_context == 'tweets':
                        user_ids = pd.read_csv(file_path)['user_id']
                    elif user_context == 'retweets':
                        user_ids = []
                        with open(file_path, encoding='utf-8', newline='') as csv_file:
                            lines = csv_file.readlines()
                            for line in lines:
                                json_str = json.loads(line)
                                user_ids.append(json_str['user']['id'])
                    else:
                        raise ValueError(f'Unknown user context {user_context}!')

                    user_ids = list(set([s for s in user_ids if isinstance(s, int)]))

                    doc_id = file.split('.')[0]

                    # only include this document ID in doc_users if we actually use it in our splits
                    if not self.doc_used(doc_id):
                        continue

                    docs_users[doc_id].update(user_ids)
                    if count == 1:
                        print(doc_id, docs_users[doc_id])
                    if count % 2000 == 0:
                        print(f"{count} done")

        print(f"\nTotal tweets/re-tweets in the data set = {count}")
        self.save_user_doc_engagements(docs_users)

    def create_feature_matrix(self):
        content_files = {}

        for label in LABELS.values():
            src_doc_files = os.path.join(self.data_raw_dir, self.dataset, label, '*')
            for folder_name in glob.glob(src_doc_files):
                content_file = folder_name + "/news content.json"
                doc_id = folder_name.split('/')[-1]
                content_files[doc_id] = content_file

        self.create_fea_matrix(content_files)

    def create_labels(self):

        self.maybe_load_id_mappings()

        # TODO same as FakeHealth, extract
        if self.n_total is None:
            adj_matrix = load_npz(self.data_complete_path(ADJACENCY_MATRIX_FILE_NAME % self.top_k))
            self.n_total = adj_matrix.shape[0]
            del adj_matrix

        print("\nLoading doc2labels dictionary...")
        doc2labels_file = self.data_complete_path(DOC_2_LABELS_FILE_NAME % self.top_k)
        if os.path.exists(doc2labels_file):
            doc2labels = json.load(open(doc2labels_file, 'r'))
        else:
            raise ValueError("Doc2labels file does not exist!")

        # split_docs = self.train_docs + self.val_docs
        # doc2labels = {}
        #
        # user_contexts = LABELS.values()
        # for user_context in user_contexts:
        #     label = 1 if user_context == 'fake' else 0
        #     for root, dirs, files in os.walk(self.data_raw_path(self.dataset, user_context)):
        #         for count, dir_name in enumerate(dirs):
        #             doc_id = dir_name
        #             if doc_id in split_docs:
        #                 doc2labels[doc_id] = label

        # print(len(doc2labels.keys()))
        # print(len(doc2id.keys()) - len(doc_splits['test_docs']))
        assert len(doc2labels.keys()) == len(self.doc2id.keys()) - len(self.test_docs)
        print(f"\nLen of doc2labels = {len(doc2labels)}")

        labels_list = np.zeros(self.n_total, dtype=int)
        for key, value in doc2labels.items():
            labels_list[self.doc2id[str(key)]] = value

        labels_file = self.data_complete_path(LABELS_FILE_NAME % self.top_k)
        print(f"\nLabels list construction done! Saving in : {labels_file}")
        save_json_file({'labels_list': list(labels_list)}, labels_file, converter=self.np_converter)

        # Create the all_labels file
        all_labels = np.zeros(self.n_total, dtype=int)
        all_labels_file = self.data_complete_path(ALL_LABELS_FILE_NAME % self.top_k)
        for doc in doc2labels.keys():
            all_labels[self.doc2id[str(doc)]] = doc2labels[str(doc)]

        print("\nSum of labels this test set = ", int(sum(all_labels)))
        print("Len of labels = ", len(all_labels))

        print(f"\nall_labels list construction done! Saving in : {all_labels_file}")
        save_json_file({'all_labels': list(all_labels)}, all_labels_file, converter=self.np_converter)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--data_raw_dir', type=str, default=RAW_DIR,
                        help='Dataset folder path that contains the folders to the raw data.')

    parser.add_argument('--data_complete_dir', type=str, default=COMPLETE_DIR,
                        help='Dataset folder path that contains the folders to the complete data.')

    parser.add_argument('--data_tsv_dir', type=str, default=TSV_DIR,
                        help='Dataset folder path that contains the folders to the intermediate data.')

    parser.add_argument('--data_set', type=str, default='gossipcop',
                        help='The name of the dataset we want to process.')

    parser.add_argument('--top_k', type=int, default=30, help='Number (in K) of top users.')

    parser.add_argument('--user_doc_threshold', type=float, default=0.3, help='Threshold defining how many articles '
                                                                              'of any class users may max have shared '
                                                                              'to be included in the graph.')

    parser.add_argument('--valid_users', type=bool, default=True, help='Flag if only top K and users not sharing '
                                                                       'more than X% of any class should be used.')

    args, unparsed = parser.parse_known_args()

    preprocessor = FakeNewsGraphPreprocessor(args.__dict__)

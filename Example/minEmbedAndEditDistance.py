import tensorflow as tf
import numpy as np
import pickle
import os,glob
import javalang
import random
import re
import sys
import getopt
import operator
import math
from scipy.spatial import distance
import edit_distance

k = 1

def main(argv):
    #http://proceedings.mlr.press/v37/kusnerb15.pdf
    global k
    chosen_datasets = None
    try:
        opts, args = getopt.getopt(argv, "hd:k:")
    except getopt.GetoptError:
        print("minSumEmbedAndEditDistance.py -k <Top k prediction> -d <Paths to datasets>")
        sys.exit()
    for opt, arg in opts:
        if opt == "-h":
            print("minSumEmbedAndEditDistance.py -k <Top k prediction> -d <Paths to datasets>")
            sys.exit()
        elif opt == "-k":
            try:
                k = int(arg)
            except ValueError:
                print("k must be integer")
                sys.exit()
        elif opt == "-d":
            chosen_datasets = arg.split(":")

    os.environ["TF_CPP_MIN_LOG_LEVEL"]="2"
    np.warnings.filterwarnings('ignore')

    tf.reset_default_graph()

    with open("Embedding_100000files_10000vol_split/dictionary.pickle" , "rb") as f:
        [count,dictionary,reverse_dictionary,vocabulary_size] = pickle.load(f)

    embedding_size = 32

    #embeddings = tf.get_variable(VARIABLE,[DIMENSION], INIT)
    embeddings = tf.get_variable("Variable"
        ,[vocabulary_size, embedding_size], initializer = tf.zeros_initializer)
    nce_weights = tf.get_variable("Variable_1"
        ,[vocabulary_size, embedding_size], initializer = tf.zeros_initializer)
    nce_biases = tf.get_variable("Variable_2"
        ,[vocabulary_size], initializer = tf.zeros_initializer)

    saver = tf.train.Saver()

    with tf.Session() as sess:
        saver.restore(sess, "Embedding_100000files_10000vol_split/model.ckpt")
        embed = embeddings.eval()

    if(chosen_datasets):
        for path_to_dataset in chosen_datasets:
            path_to_tasks = os.path.join(path_to_dataset, "Tasks/")
            for task in os.listdir(path_to_tasks):
                if(task.endswith(".txt")):
                    path_to_task = os.path.abspath(os.path.join(path_to_tasks, task))
                    predict(path_to_task, embedding_size, dictionary, embed)
    else:
        path_to_current = os.path.abspath(os.path.dirname(__file__))
        path_to_datasets = os.path.join(path_to_current, "../Datasets/")

        for dataset_dir in os.listdir(path_to_datasets):
            path_to_dataset = os.path.join(path_to_datasets, dataset_dir)
            if(os.path.isdir(path_to_dataset)):
                path_to_tasks = os.path.join(path_to_dataset, "Tasks/")
                for task in os.listdir(path_to_tasks):
                    if(task.endswith(".txt")):
                        path_to_task = os.path.abspath(os.path.join(path_to_tasks, task))
                        predict(path_to_task, embedding_size, dictionary, embed)


def predict(path_to_task, embedding_size, dictionary, embed):
    global k
    with open(path_to_task, 'r') as file:
        lines = file.readlines()

        # Get inserted code
        insert = lines[0]
        insert_tokens = javalang.tokenizer.tokenize(insert)
        insert_unk = []

        # Calculate the avg embedding
        try:
            insert_embed = []
            for token in insert_tokens:
                if(not dictionary.get(token.value, 0) == 0):
                    insert_embed.append(embed[dictionary.get(token.value)])
                else:
                    insert_unk.append(token.value)
            if(not insert_embed and not insert_unk):
                return
        except javalang.tokenizer.LexerError:
            return

        # The rest is the program
        lines = lines[2:]
        file_length = len(lines)
        lines_string = "".join(lines)
        program_tokens = javalang.tokenizer.tokenize(lines_string)

        # Calculate the avg embedding of each line
        program_embed_vectors = [[] for _ in range(file_length)]
        program_unk = [[] for _ in range(file_length)]
        try:
            for token in program_tokens:
                (row, col) = token.position
                if(dictionary.get(token.value, 0) == 0):
                    program_unk[row-1].append(token.value)
                else:
                    token_embedding = embed[dictionary.get(token.value)]
                    program_embed_vectors[row-1].append(token_embedding)
        except javalang.tokenizer.LexerError:
            return

        # Compute cosine similarity
        score = {}
        maxEdit = float('-Inf')
        maxEmbed = float('-Inf')
        for i in range(0, file_length):
            if(not program_embed_vectors[i] and not program_unk[i]):
                score[i+1] = float('Inf')
            elif(not program_embed_vectors[i]):
                if(not insert_embed):
                    if(''.join(insert.split()) == ''.join(lines[i].split())):
                        score[i+1] = 0
                    else:
                        score[i+1] = min_cum_edit_distance(insert_unk,program_unk[i])
                else:
                    if(''.join(insert.split()) == ''.join(lines[i].split())):
                        score[i+1] = 0
                    else:
                        score[i+1] = min_cum_edit_distance(insert_unk,program_unk[i])
                    if(score[i+1] > maxEdit):
                        maxEdit = score[i+1]
            elif(not program_unk[i]):
                if(not insert_unk):
                    if(''.join(insert.split()) == ''.join(lines[i].split())):
                        score[i+1] = 0
                    else:
                        score[i+1] = min_cum_embed_distance(insert_embed,program_embed_vectors[i])
                else:
                    if(''.join(insert.split()) == ''.join(lines[i].split())):
                        score[i+1] = 0
                    else:
                        score[i+1] = min_cum_embed_distance(insert_embed,program_embed_vectors[i])
                    if(score[i+1] > maxEmbed):
                        maxEmbed = score[i+1]
            else:
                if(''.join(insert.split()) == ''.join(lines[i].split())):
                    score[i+1] = 0
                else:
                    score[i+1] = math.sqrt(min_cum_edit_distance(insert_unk,program_unk[i])*min_cum_embed_distance(insert_embed,program_embed_vectors[i]))


        #print(str(minEdit) + " " + str(minEmbed))
        for i in range(0, file_length):
            if(not program_embed_vectors[i] and program_unk[i]):
                if(insert_embed and not maxEmbed == float('-Inf')):
                    score[i+1] = math.sqrt(score[i+1]*maxEmbed)
            if(program_embed_vectors[i] and not program_unk[i]):
                if(insert_unk and not maxEdit == float('-Inf')):
                    score[i+1] = math.sqrt(score[i+1]*maxEdit)


        sorted_score = sorted(score.items(), key=operator.itemgetter(1))

        guess_string = ""
        for i in range(0,min(k, len(sorted_score))):
            guess_string = guess_string + str(sorted_score[i][0]) + " "

        print(path_to_task + " " + guess_string)

def min_cum_embed_distance(insert_embed, program_embed):
    score = 1
    for i in range(0, len(insert_embed)):
        min_distance = float('Inf')
        for j in range(0, len(program_embed)):
            d = distance.euclidean(insert_embed[i],program_embed[j])
            if(d < min_distance):
                min_distance = d
        score += min_distance
    return score

def min_cum_edit_distance(insert_unk, program_unk):
    score = 1
    for i in range(0, len(insert_unk)):
        min_distance = float('Inf')
        for j in range(0, len(program_unk)):
            d = editDistance(insert_unk[i], program_unk[j])
            if(d < min_distance):
                min_distance = d
        score += min_distance
    return score

def editDistance(s1,s2):
    return edit_distance.SequenceMatcher(a=s1, b=s2).distance()

if __name__=="__main__":
    main(sys.argv[1:])

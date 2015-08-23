#!/usr/bin/python3

from knp.knpinfo import preprocess_sentence
import sys
if __name__ == '__main__':
    for sent in sys.stdin:
        if sent[0] == ' ':
            sent = sent[1:]
        print(preprocess_sentence(sent), end='')
        sys.stdout.flush()


                

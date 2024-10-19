import datetime
import math
import re

from pydantic import BaseModel
from openai import OpenAI
from server.secrets import OPENAIAPI_KEY
import sqlite3
from datetime import datetime, timedelta


DB_PATH = "db.sqlite3"
client = OpenAI(api_key=OPENAIAPI_KEY)


class Sentence(BaseModel):
    english: str
    translation: str
    topic: str


class Sentences(BaseModel):
    sentences: list[Sentence]


class Topics(BaseModel):
    topics: list[str]


# models = client.models.list()
#
# print("models", models)

def get_topics_from_llm():
    topics_completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a language tutor"},
            {"role": "user", "content": "Please give a list of ten topics or categories on which to practice language "
                                        "learning. For example: [food, technology, the past tense]. Give only a single"
                                        "topic per item."},
        ],
        response_format=Topics,
    )

    return topics_completion.choices[0].message.parsed


def get_sentences_from_llm(language, topic) -> list[Sentence]:
    sentences_completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a language tutor"},
            {"role": "user", "content": f"Provide a list of sentences for an English speaker learning {language} to practice"
                                        f"based on the following topic: {topic}"},
        ],
        response_format=Sentences,
    )
    return sentences_completion.choices[0].message.parsed.sentences


def get_sentences_from_db(language, topic) -> list[Sentence]:
    connection = None
    try:
        # Connect to the SQLite database
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        # Execute the provided query
        cursor.execute("SELECT english, translation, topic FROM sentences WHERE language = ? AND topic = ?",
                       (language, topic))

        # Fetch all results from the executed query
        results = cursor.fetchall()

        return [Sentence(english=result[0], translation=result[1], topic=result[2]) for result in results]
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return []
    finally:
        # Ensure the connection is closed properly
        if connection:
            connection.close()


def store_sentences_in_db(language, sentences: list[Sentence]):
    try:
        # Connect to the SQLite database
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        for sentence in sentences:
            cursor.execute(f"INSERT INTO sentences (language, english, translation, topic) VALUES (?, ?, ?, ?)",
                           (language, sentence.english, sentence.translation, sentence.topic))

        # Commit the transaction
        print("Commited", connection.commit())

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")


def get_word_scores_from_db(language, words):
    connection = None
    try:
        # Connect to the SQLite database
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        # Execute the provided query
        placeholders = ', '.join(['?'] * len(words))
        cursor.execute(f"SELECT word, score, last_seen FROM word_scores WHERE language = ? AND "
                       f"word IN ({placeholders})", (language, ) + tuple(words))

        # Fetch all results from the executed query
        return cursor.fetchall()
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return []
    finally:
        # Ensure the connection is closed properly
        if connection:
            connection.close()


def get_word_scores(language, words) -> list[float]:
    word_scores = get_word_scores_from_db(language, words)
    format_string = "%Y-%m-%d %H:%M:%S"
    word_scores = {word: (score, datetime.strptime(last_seen, format_string)) for word, score, last_seen in word_scores}
    # Default the score to 10 for any words we don't yet have in the db
    cur_time = datetime.now()

    adjusted_scores = []
    seconds_in_day = 60 * 60 * 24
    for word in words:
        score, last_seen = word_scores.get(word, (10, cur_time - timedelta(days=5)))
        time_difference = cur_time - last_seen
        adjusted_score = (-100/score) * (time_difference.total_seconds() / seconds_in_day) + 100
        adjusted_scores.append(adjusted_score)
    return adjusted_scores


def calculate_sentence_score(word_scores) -> float:
    return sum(word_scores) / len(word_scores)


def calculate_sentence_scores(language: str, sentences: list[Sentence]):
    results = []
    # Use the user's word scores to calculate a score for the sentences
    for sentence in sentences:
        text = re.sub(r'[^\w\'\s]', '', sentence.translation)
        words = text.lower().split()
        word_scores = get_word_scores(language, words)
        sentence_score = calculate_sentence_score(word_scores)
        results.append((sentence, sentence_score))
    return results


def update_word_scores_in_db(language, word_scores):
    connection = None
    try:
        # Connect to the SQLite database
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        for word_score in word_scores:
            # Execute the provided query
            cursor.execute(f"INSERT OR REPLACE INTO word_scores (language, word, score, last_seen) VALUES "
                           f"(?, ?, ?, datetime())", (language, ) + word_score)

        print("Scores commited", connection.commit())
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return []
    finally:
        # Ensure the connection is closed properly
        if connection:
            connection.close()


def update_word_scores(language, sentence, original_word_matches):

    text = re.sub(r'[^\w\'\s]', '', sentence.translation)
    words = text.lower().split()
    current_word_scores = get_word_scores(language, words)

    new_word_scores = []

    for i in range(len(original_word_matches)):
        match = original_word_matches[i]
        cur_score = current_word_scores[i]
        correct = match[2] >= 0  # if the index is >= 0 this means the word was found in the entry
        if correct:
            # new_score = min(100.0, cur_score + math.sqrt(100-cur_score))
            new_score = min(100.0, cur_score + 5)
            print(f"Updating score for correct word {match[0]} from {cur_score} to {new_score}")
        else:
            new_score = max(0.0, cur_score - 5)
            # new_score = max(0.0, cur_score - math.sqrt(cur_score))
            print(f"Updating score for incorrect word {match[0]} from {cur_score} to {new_score}")
        new_word_scores.append((match[0], new_score))

    update_word_scores_in_db(language, new_word_scores)


def find_matches_in_strings(str1, str2):
    str2matches = {}
    str1_words = []

    for word_match in re.finditer(r'[\w\']+', str1):
        word = word_match.group()
        str1_idx = word_match.start()
        prev_str2_idx = str2matches.get(word, -1)

        str2_idx = -1

        # Search the other string for the same word
        for str2_match in re.finditer(rf"\b{word}\b", str2, re.IGNORECASE):
            if str2_match.start() > prev_str2_idx:
                str2_idx = str2_match.start()
                str2matches[word] = str2_idx
                break

        str1_words.append((word, str1_idx, str2_idx))

    return str1_words


def all_words_match(matches1, matches2):
    if len(matches1) != len(matches2):
        return False

    # Return true if all words have a position in the other sentence
    if not all(elem[2] >= 0 for elem in matches1):
        return False
    if not all(elem[2] >= 0 for elem in matches2):
        return False

    # Now make sure all the words are in the right order
    for i in range(len(matches1)):
        if matches1[i][0] != matches2[i][0]:
            return False

    return True


def find_matches_with_positions(str1, str2):
    str1_words = find_matches_in_strings(str1, str2)
    str2_words = find_matches_in_strings(str2, str1)
    correct = all_words_match(str1_words, str2_words)

    return str1_words, str2_words, correct

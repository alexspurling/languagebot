import datetime
import math
import re

from pydantic import BaseModel
from openai import OpenAI
from server.secrets import OPENAIAPI_KEY
import sqlite3
from datetime import datetime, timedelta

from difflib import SequenceMatcher


DB_PATH = "db.sqlite3"
client = OpenAI(api_key=OPENAIAPI_KEY)


class Sentence(BaseModel):
    english: str
    translations: list[str]
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


def get_prompt(language, topic):
    prompt = f"""
    Provide a list of sentences for an English speaker learning {language} 
    to practice based on the following topic: {topic}. Each sentence should
    be given in English and list of equivalent {language} translations. Make
    sure you enumerate all possible grammatically correct translations including
    combinations that include any optional pronouns or prepositions and include
    variations for each possible combination of plurality, gender and formality.
    All translations should match the original English sentence in terms of
    vocabulary. For example, here's a sentence which varies depending on whether
    the you is singular or plural and whether prepositions are included or not:
    """
    examples = """
    {
      "sentence": {
        "language": "Italian",
        "english": "I want you to go",
        "translations": [
          "Voglio che tu vada.",
          "Voglio che vada",
          "Voglio che lei vada",
          "Voglio che voi andiate",
          "Voglio che andiate",
          "Voglio che loro vadano",
          "Voglio che vadano"
        ]
      }
    }
    
    Here's a sentence that varies based on whether the speaker is male or female:
    
    {
      "sentence": {
        "language": "French",
        "english": "I am happy",
        "translations": [
          "Je suis heureux",
          "Je suis heureuse"
        ]
      }
    }
    
    Here's a sentence that varies based on level for formality:
    
    {
      "sentence": {
        "language": "Japanese",
        "english": "Hello, how are you?",
        "translations": [
          "Yā, genki?",
          "Konnichiwa, genki?",
          "Konnichiwa, ogenki desu ka?",
          "Konnichiwa, ikaga osugoshi desu ka?",
          "Konnichiwa, gokigen ikaga desu ka?",
          "Go-aisatsu mōshiagemasu. Ogenki de irasshaimasu ka?",
          "Haikei, ogenki de irasshaimasu ka?",
        ]
      }
    }
    """
    return prompt + examples


def get_sentences_from_llm(language, topic) -> list[Sentence]:
    sentences_completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a language tutor"},
            {"role": "user", "content": get_prompt(language, topic)}
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
        cursor.execute("SELECT english, translation FROM sentences WHERE language = ? AND topic = ? ORDER BY english",
                       (language, topic))

        # Fetch all results from the executed query
        results = cursor.fetchall()

        sentences = []
        translations = []
        last_english = None
        for result in results:
            if result[0] != last_english:
                if last_english is not None:
                    sentences.append(Sentence(english=last_english, translations=translations, topic=topic))
                translations = []
            translations.append(result[1])
            last_english = result[0]

        if last_english is not None:
            sentences.append(Sentence(english=last_english, translations=translations, topic=topic))

        return sentences
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return []
    finally:
        # Ensure the connection is closed properly
        if connection:
            connection.close()


def get_sentence_from_db(language, english) -> Sentence | None:
    connection = None
    try:
        # Connect to the SQLite database
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        # Execute the provided query
        cursor.execute("SELECT translation, topic FROM sentences WHERE language = ? AND english = ?",
                       (language, english))

        # Fetch all results from the executed query
        results = cursor.fetchall()

        if len(results) == 0:
            return None

        translations = [result[0] for result in results]
        topic = results[0][1]

        return Sentence(english=english, translations=translations, topic=topic)
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return None
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
            for translation in sentence.translations:
                cursor.execute(f"INSERT OR IGNORE INTO sentences (language, english, translation, topic) "
                               f"VALUES (?, ?, ?, ?)", (language, sentence.english, translation, sentence.topic))

        # Commit the transaction
        connection.commit()
        print("Sentences commited")

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
    cur_time_utc = datetime.now()

    # print("cur_time", cur_time, cur_time.timestamp())
    # print("cur_time_utc", cur_time_utc, cur_time_utc.timestamp())

    adjusted_scores = []
    seconds_in_day = 60 * 60 * 24
    for word in words:
        score, last_seen = word_scores.get(word, (10, cur_time - timedelta(days=5)))
        time_difference = cur_time - last_seen
        adjusted_score = (-100/score) * (time_difference.total_seconds() / seconds_in_day) + 100
        adjusted_scores.append(adjusted_score)
    return adjusted_scores


def calculate_translation_score(language: str, translation: str):
    words = split_words(translation)
    word_scores = get_word_scores(language, words)
    return sum(word_scores) / len(word_scores)


def calculate_sentence_scores(language: str, sentences: list[Sentence]):
    results = []
    # Use the user's word scores to calculate a score for the sentences
    for sentence in sentences:
        # The sentence score is the maximum score for all the different possible translations
        sentence_score = max([calculate_translation_score(language, translation) for translation in sentence.translations])
        results.append((sentence, sentence_score))
        print("Sentence", sentence.english, "score: ", sentence_score)
    return results


def update_word_scores_in_db(language, word_scores):
    connection = None
    try:
        # Connect to the SQLite database
        connection = sqlite3.connect(DB_PATH)
        cursor = connection.cursor()

        for word_score in word_scores:
            # Execute the provided query
            cursor.execute("INSERT INTO word_scores (language, word, score, last_seen) VALUES "
                           "(?, ?, ?, datetime()) "
                           "ON CONFLICT (language, word) "
                           "DO UPDATE SET score = excluded.score, last_seen = excluded.last_seen",
                           (language, ) + word_score)

        connection.commit()
        print("Scores commited")
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return []
    finally:
        # Ensure the connection is closed properly
        if connection:
            connection.close()


def update_word_scores(language, translation, original_word_matches):

    words = split_words(translation)

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


def split_words(translation):
    words = []
    for word_match in re.finditer(r'[\w\']+', translation):
        words.append(word_match.group())
    return words


def find_best_translation(sentence, submission):
    # First see if we can find an exact match
    for translation in sentence.translations:
        if submission == translation:
            return translation

    best_translation = None
    best_translation_score = 0

    for translation in sentence.translations:
        s = SequenceMatcher(None, translation, submission)
        if s.ratio() > best_translation_score:
            best_translation_score = s.ratio()
            best_translation = translation

    return best_translation


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
        if matches1[i][0].casefold() != matches2[i][0].casefold():  # TODO use proper normalisation to compare strings
            return False

    return True


def find_matches_with_positions(str1, str2):
    str1_words = find_matches_in_strings(str1, str2)
    str2_words = find_matches_in_strings(str2, str1)
    correct = all_words_match(str1_words, str2_words)

    return str1_words, str2_words, correct

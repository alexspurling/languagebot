import json

from django.http import JsonResponse, HttpResponseBadRequest
from django.views import View

from server.languagebot import (get_sentence_from_db, get_sentences_from_db, calculate_sentence_scores,
                                get_sentences_from_llm, store_sentences_in_db, find_matches_with_positions,
                                update_word_scores, find_best_translation)

TARGET_SCORE = 65


class GetSentenceView(View):

    # Get a sentence with the given topic
    def post(self, request):
        body = json.loads(request.body)

        language = body["language"]
        topic = body["topic"].lower().strip()

        print(f"Request for sentence with language {language}, topic {topic}")

        # Either try to get the best sentence from the db or load more from chatgpt

        sentences = get_sentences_from_db(language, topic)

        print("Sentences from db", sentences)

        if not sentences:
            print("No sentences available in the database for topic. Getting sentences from LLM...")
            sentences = get_sentences_from_llm(language, topic)
            print("Sentences from llm", sentences)

            store_sentences_in_db(language, sentences)

        sentences_with_scores = calculate_sentence_scores(language, sentences)

        print("Sentence scores ", sentences_with_scores)

        # def sort_to_target_score(s):
        #     print("Sorting ", s, "Value:", abs(s[1] - TARGET_SCORE))
        #     return TARGET_SCORE - s[1]

        # Find the sentence with the best scores
        sorted_sentences = sorted(sentences_with_scores, key=lambda s: abs(TARGET_SCORE - s[1]))

        print("Sorted sentences", sorted_sentences)

        best_sentence = sorted_sentences[0][0]

        # if the best sentence score is too far from the target then request some more
        # if abs(sorted_sentences[0][1] - TARGET_SCORE) > 20:
        #     print("Target score is more than 20 away. Getting some new sentences from LLM")
        #     sentences = get_sentences_from_llm(language, topic)
        #     print("Sentences from llm", sentences)
        #
        #     store_sentences_in_db(language, sentences)
        #
        #     sentences_with_scores = calculate_sentence_scores(language, sentences)
        #
        #     print("Sentence scores ", sentences_with_scores)
        #
        #     # Find the sentence with the best scores
        #     sorted_sentences = sorted(sentences_with_scores, key=lambda s: abs(TARGET_SCORE - s[1]))
        #
        #     print("Sorted sentences", sorted_sentences)
        #
        #     best_sentence = sorted_sentences[0][0]

        return JsonResponse({"english": best_sentence.english}, status=200)


class SubmitSentenceView(View):

    # Submit a sentence with the given topic
    def post(self, request):
        body = json.loads(request.body)

        language = body["language"]
        english = body["english"]
        submission = body["submission"]
        sentence = get_sentence_from_db(language, english)

        if sentence is None:
            print("Error can't find sentence with English " + english + " in the database.")
            return HttpResponseBadRequest("Invalid english sentence")

        print("Language", language, "Submitted", submission, "sentence", sentence)

        # Check if any translations are an exact match
        translation = find_best_translation(sentence, submission)

        # Compare the pre-calculated translation and the submission
        original_word_matches, entered_word_matches, correct = \
            find_matches_with_positions(translation, submission)

        # Update our word scores
        update_word_scores(language, translation, original_word_matches)

        return JsonResponse({"original_word_matches": original_word_matches,
                             "entered_word_matches": entered_word_matches, "correct": correct,
                             "translation": translation}, status=200)

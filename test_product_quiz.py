import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg
import streamlit as st
from streamlit.testing.v1 import AppTest

from product_quiz import QUESTION_SETS
from result_store import TEST_CONSENT_VERSION


EXPECTED_ANSWERS = {
    "바이고 액상수화제": [
        "개화 기간이 길어 순나방·심식나방 밀도가 높아질 수 있기 때문",
        "열매 내부로 들어가기 전, 표면을 섭식하는 1~2령 유충",
        "정식 전 육묘상 침지처리",
        "디아마이드계 연용을 피하고 다른 작용기작 약제와 교호살포한다",
        "꽃이 피어 있는 시기에는 살포하지 않는다",
    ],
    "모벤토 액상수화제": [
        "해충 발생 초기에, 잎이 충분히 확보된 상태에서 충분한 약량을 살포한다",
        "물관·체관을 통한 이동을 활용하되 결구 시작 전에 처리한다",
        "가루깍지벌레",
        "깍지벌레가 봉지 속으로 이동하는 것을 줄여 피해과를 줄이기 위해",
        "성충은 시반토, 약충은 모벤토를 활용한다",
    ],
}


class FieldGuideQuizTests(unittest.TestCase):
    def setUp(self):
        save_patch = patch("result_store.save_submission")
        self.save_submission = save_patch.start()
        self.addCleanup(save_patch.stop)
        secrets_patch = patch("streamlit.secrets", {"postgres": {
            "host": "test.invalid", "port": 5432, "dbname": "postgres",
            "user": "test", "password": "", "sslmode": "require",
        }})
        secrets_patch.start()
        self.addCleanup(secrets_patch.stop)

    def registered_app(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
        app.text_input(key="participant_name_input").set_value(" 테스트 응시자 ")
        app.text_input(key="participant_affiliation_input").set_value(" 테스트 소속 ")
        app.checkbox(key="participant_consent_input").check()
        app.button(key="register_participant").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["step"], "START")
        return app

    def test_preview_requires_password_before_participant_registration(self):
        with patch.dict("os.environ", {"QUIZ_PREVIEW_PASSWORD": "demo-preview-password"}):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.text_input), 1)
            self.assertFalse(app.selectbox)
            for incorrect in ["", "incorrect", "잘못된 비밀번호"]:
                app.text_input[0].set_value(incorrect)
                app.button(key="enter_preview").click().run()
                self.assertFalse(app.exception)
                self.assertIn("일치하지 않습니다", app.error[0].value)
                self.assertFalse(app.session_state.get("preview_authenticated", False))
                self.assertEqual(len(app.text_input), 1)
            app.text_input[0].set_value("demo-preview-password")
            app.button(key="enter_preview").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["step"], "REGISTER")
            self.assertTrue(app.session_state["preview_authenticated"])
            app.run()
            self.assertTrue(app.text_input(key="participant_name_input"))
            another = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
            self.assertEqual(len(another.text_input), 1)
            self.assertFalse(another.session_state.get("preview_authenticated", False))
            self.save_submission.assert_not_called()

    def test_empty_preview_password_blocks_access(self):
        with patch.dict("os.environ", {"QUIZ_PREVIEW_PASSWORD": ""}):
            app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
            self.assertFalse(app.exception)
            self.assertIn("설정되지 않았습니다", app.error[0].value)
            self.assertFalse(app.text_input)
            self.save_submission.assert_not_called()

    def test_registration_requires_name_affiliation_and_consent(self):
        for name, affiliation, consent, message in [
            ("   ", "테스트 소속", True, "이름을 입력"),
            ("테스트 응시자", "   ", True, "소속을 입력"),
            ("테스트 응시자", "테스트 소속", False, "동의한 후"),
        ]:
            with self.subTest(message=message):
                app = AppTest.from_file(str(Path(__file__).with_name("app.py"))).run()
                app.text_input(key="participant_name_input").set_value(name)
                app.text_input(key="participant_affiliation_input").set_value(affiliation)
                app.checkbox(key="participant_consent_input").set_value(consent)
                app.button(key="register_participant").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["step"], "REGISTER")
                self.assertIsNone(app.session_state["participant"])
                self.assertIn(message, app.error[0].value)
                self.assertFalse(app.selectbox)

    def test_participant_change_requires_new_consent(self):
        app = self.registered_app()
        self.assertEqual(app.session_state["participant"]["name"], "테스트 응시자")
        self.assertEqual(app.session_state["participant"]["affiliation"], "테스트 소속")
        self.assertTrue(app.session_state["participant"]["consent_given"])
        self.assertEqual(app.session_state["participant"]["consent_version"], TEST_CONSENT_VERSION)
        self.assertIsNotNone(app.session_state["participant"]["consent_at"].tzinfo)
        app.button(key="change_participant").click().run()
        self.assertEqual(app.session_state["step"], "REGISTER")
        self.assertFalse(app.checkbox(key="participant_consent_input").value)
        app.text_input(key="participant_name_input").set_value("다른 응시자")
        app.text_input(key="participant_affiliation_input").set_value("다른 소속")
        app.checkbox(key="participant_consent_input").check()
        app.button(key="register_participant").click().run()
        app.button(key="start_mission").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["game_data"]["participant_name"], "다른 응시자")
        self.assertEqual(app.session_state["game_data"]["participant_affiliation"], "다른 소속")

    def test_product_selection_category_badges(self):
        app = self.registered_app()
        for product, category, color in [
            ("알리온플러스 액상수화제", "제초제", "yellow"),
            ("나티보 액상수화제", "살균제", "violet"),
            ("모벤토 액상수화제", "살충제", "blue"),
        ]:
            with self.subTest(category=category):
                app.selectbox(key="product_picker").select(product).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.subheader[0].value, "제품 선택")
                self.assertTrue(any(
                    item.value == f":{color}-badge[{category}]" for item in app.markdown
                ))

    def test_answers_remain_correct_after_option_rotation(self):
        for product, expected in EXPECTED_ANSWERS.items():
            questions = QUESTION_SETS[product]
            self.assertEqual(len(questions), 5)
            for question, answer in zip(questions, expected):
                with self.subTest(question=question["question_id"]):
                    self.assertEqual(question["options"][question["correct_option"]], answer)
                    self.assertEqual(len(set(question["options"].values())), 4)
                    self.assertIsNone(question["source_url"])
                    self.assertIn("현장 처방 가이드_v8.pptx", question["source_label"])
                    self.assertIn("최신 제품 라벨", question["correct_feedback_html"])

    def test_both_products_complete_with_slide_sources(self):
        for product in EXPECTED_ANSWERS:
            with self.subTest(product=product):
                app = self.registered_app()
                app.selectbox(key="product_picker").select(product).run()
                app.button(key="start_mission").click().run()
                for question in QUESTION_SETS[product]:
                    self.assertFalse(app.exception)
                    self.assertFalse(any("문항 출처:" in item.value for item in app.caption))
                    correct = question["correct_option"]
                    app.radio[0].set_value(f"{correct}. {question['options'][correct]}").run()
                    app.button[0].click().run()
                    self.assertFalse(app.exception)
                    self.assertTrue(any(question["source_label"] in item.value for item in app.caption))
                    self.assertEqual(app.session_state["game_data"]["source_label"], question["source_label"])
                    app.button[0].click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["step"], "RESULT")
                self.assertEqual(len(app.session_state["results"]), 5)
                self.assertTrue(all(result["is_correct"] for result in app.session_state["results"]))
                self.assertEqual(sum("문항 출처:" in item.value for item in app.caption), 5)
                for result in app.session_state["results"]:
                    self.assertEqual(result["participant_name"], "테스트 응시자")
                    self.assertEqual(result["participant_affiliation"], "테스트 소속")
                    self.assertTrue(result["participant_consent"])
                self.assertTrue(any("테스트 응시자" in item.value for item in app.text))
                saved = self.save_submission.call_args.args[1]
                self.assertEqual(saved["participant_name"], "테스트 응시자")
                self.assertEqual(saved["correct_count"], 5)
                self.assertEqual(saved["total_points"], 750)
                self.assertEqual(saved["answers"], app.session_state["results"])
                save_calls = self.save_submission.call_count
                app.run()
                self.assertEqual(self.save_submission.call_count, save_calls)
                app.button(key="return_to_lobby").click().run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state["participant"]["name"], "테스트 응시자")
                self.assertEqual(app.session_state["results"], [])

    def test_source_is_shown_after_second_wrong_attempt(self):
        product = "모벤토 액상수화제"
        question = QUESTION_SETS[product][0]
        app = self.registered_app()
        app.selectbox(key="product_picker").select(product).run()
        app.button(key="start_mission").click().run()
        wrong = next(key for key in question["options"] if key != question["correct_option"])
        app.radio[0].set_value(f"{wrong}. {question['options'][wrong]}").run()
        app.button[0].click().run()
        self.assertFalse(any("문항 출처:" in item.value for item in app.caption))
        app.button[0].click().run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(question["source_label"] in item.value for item in app.caption))

    def test_result_cards_preserve_answers_and_attempt_details(self):
        product = "카운실 액상수화제"
        questions = QUESTION_SETS[product]
        results = []
        for index, question in enumerate(questions):
            is_correct = index >= 3
            selected = question["correct_option"] if is_correct else next(
                key for key in question["options"] if key != question["correct_option"]
            )
            results.append({
                "selected_option": selected,
                "is_correct": is_correct,
                "attempt_count": 2 if index == 1 else 1,
                "hint_used": index == 1,
                "response_time_seconds": 12.48,
                "earned_points": 150 if is_correct else 50,
            })
        app = self.registered_app()
        app.selectbox(key="product_picker").select(product).run()
        app.button(key="start_mission").click().run()
        app.session_state["results"] = results
        app.session_state["quiz_completed_at"] = datetime.now(timezone.utc)
        app.session_state["step"] = "RESULT"
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual([metric.value for metric in app.metric], ["2 / 5", "450 P"])
        self.assertFalse(any("|---" in item.value for item in app.markdown))
        for question, result in zip(questions, results):
            card = app.get_by_key(f"result_{question['question_id']}")
            selected = result["selected_option"]
            self.assertTrue(any(
                item.value == f"선택한 답: {selected}. {question['options'][selected]}"
                for item in card.markdown
            ))
            self.assertIn("정답" if result["is_correct"] else "오답", card.markdown[0].value)
            self.assertIn(f"시도 {result['attempt_count']} / 2회", card.caption[0].value)
            self.assertIn("힌트 사용" if result["hint_used"] else "힌트 미사용", card.caption[0].value)
            self.assertIn("12.48초", card.caption[0].value)
            self.assertFalse(card.expander[0].proto.expanded)
        self.assertFalse(app.json)
        self.assertEqual(len(app.expander), len(questions))
        self.assertEqual(app.session_state["results"], results)

    def test_game_hud_tracks_retry_hint_reward_and_completed_stages(self):
        product = "바이고 액상수화제"
        question = QUESTION_SETS[product][0]
        app = self.registered_app()
        app.selectbox(key="product_picker").select(product).run()
        app.button(key="start_mission").click().run()
        self.assertEqual([metric.value for metric in app.metric], ["0 P", "2 / 2"])
        wrong = next(key for key in question["options"] if key != question["correct_option"])
        app.radio[0].set_value(f"{wrong}. {question['options'][wrong]}").run()
        app.button(key="submit_answer").click().run()
        self.assertEqual([metric.value for metric in app.metric], ["50 P", "1 / 2"])
        app.button(key="retry_mission").click().run()
        app.checkbox[0].check().run()
        correct = question["correct_option"]
        app.radio[0].set_value(f"{correct}. {question['options'][correct]}").run()
        app.button(key="submit_answer").click().run()
        self.assertFalse(app.exception)
        self.assertEqual([metric.value for metric in app.metric], ["120 P", "CLEAR"])
        app.run()
        self.assertEqual(app.metric[0].value, "120 P")
        app.button(key="next_mission").click().run()
        self.assertFalse(app.exception)
        self.assertEqual([metric.value for metric in app.metric], ["120 P", "2 / 2"])
        self.assertEqual(app.progress[0].value, 20)
        self.assertTrue(any("01 완료" in item.value for item in app.markdown))

    def test_failed_cloud_save_retains_results_and_retries_same_submission(self):
        self.save_submission.side_effect = [psycopg.OperationalError(), None]
        app = self.registered_app()
        app.button(key="start_mission").click().run()
        submission_id = app.session_state["submission_id"]
        results = [{
            "selected_option": question["correct_option"], "is_correct": True,
            "attempt_count": 1, "hint_used": False,
            "response_time_seconds": 1.0, "earned_points": 150,
        } for question in QUESTION_SETS[app.session_state["active_product"]]]
        app.session_state["results"] = results
        app.session_state["quiz_completed_at"] = datetime.now(timezone.utc)
        app.session_state["step"] = "RESULT"
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertFalse(app.success)
        self.assertTrue(app.button(key="return_to_lobby").disabled)
        self.assertEqual(app.session_state["results"], results)
        app.button(key="retry_save").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)
        self.assertFalse(app.button(key="return_to_lobby").disabled)
        self.assertEqual(self.save_submission.call_count, 2)
        for call in self.save_submission.call_args_list:
            self.assertEqual(call.args[1]["submission_id"], submission_id)

    def test_interrupted_save_recovers_result_report(self):
        def interrupt_once(settings, submission):
            self.save_submission.side_effect = None
            st.rerun()

        self.save_submission.side_effect = interrupt_once
        app = self.registered_app()
        app.button(key="start_mission").click().run()
        submission_id = app.session_state["submission_id"]
        results = [{
            "selected_option": question["correct_option"], "is_correct": True,
            "attempt_count": 1, "hint_used": False,
            "response_time_seconds": 1.0, "earned_points": 150,
        } for question in QUESTION_SETS[app.session_state["active_product"]]]
        app.session_state["results"] = results
        app.session_state["quiz_completed_at"] = datetime.now(timezone.utc)
        app.session_state["step"] = "RESULT"
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)
        self.assertEqual(len(app.expander), 5)
        self.assertEqual(app.session_state["results"], results)
        self.assertEqual(self.save_submission.call_count, 2)
        for call in self.save_submission.call_args_list:
            self.assertEqual(call.args[1]["submission_id"], submission_id)

        del app.session_state["result_saved"]
        del app.session_state["save_error"]
        app.session_state["save_attempted"] = True
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(app.success)
        self.assertEqual(self.save_submission.call_count, 3)
        self.assertEqual(self.save_submission.call_args.args[1]["submission_id"], submission_id)


if __name__ == "__main__":
    unittest.main()

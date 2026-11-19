import unittest
from scoring import ScoringService

class DummyAttempt:
    def __init__(self, username, wpm, accuracy, elapsed_seconds, incorrect_attempts, is_completed=True, status='completed'):
        self.username = username
        self.wpm = wpm
        self.accuracy = accuracy
        self.elapsed_seconds = elapsed_seconds
        self.incorrect_attempts = incorrect_attempts
        self.is_completed = is_completed
        self.status = status

class TestScoringAndRanking(unittest.TestCase):

    def test_wpm_calculation(self):
        # 250 correct characters in 60 seconds (1 min) = 50 WPM
        wpm = ScoringService.calculate_wpm(correct_chars=250, elapsed_seconds=60.0)
        self.assertEqual(wpm, 50.0)

        # 300 correct characters in 30 seconds (0.5 min) = (300/5)/0.5 = 120 WPM
        wpm = ScoringService.calculate_wpm(correct_chars=300, elapsed_seconds=30.0)
        self.assertEqual(wpm, 120.0)

        # 0 elapsed seconds or 0 chars handles cleanly without ZeroDivisionError
        self.assertEqual(ScoringService.calculate_wpm(0, 0), 0.0)
        self.assertEqual(ScoringService.calculate_wpm(100, 0), 0.0)
        self.assertEqual(ScoringService.calculate_wpm(0, 50), 0.0)

    def test_accuracy_calculation(self):
        # 95 correct out of 100 total scored = 95.0%
        acc = ScoringService.calculate_accuracy(correct_keystrokes=95, total_scored_keystrokes=100)
        self.assertEqual(acc, 95.0)

        # 0 total scored keystrokes returns 100.0 baseline
        self.assertEqual(ScoringService.calculate_accuracy(0, 0), 100.0)

    def test_event_replay_and_scoring(self):
        target = "Hello World"
        events = [
            {"seq": 1, "type": "insert", "char": "H"},
            {"seq": 2, "type": "insert", "char": "e"},
            {"seq": 3, "type": "insert", "char": "l"},
            {"seq": 4, "type": "insert", "char": "x"}, # Incorrect char
            {"seq": 5, "type": "backspace"},           # Backspace correction
            {"seq": 6, "type": "insert", "char": "l"},
            {"seq": 7, "type": "insert", "char": "o"},
        ]

        result = ScoringService.apply_events(target_text=target, events=events)
        self.assertTrue(result['success'])
        self.assertEqual(result['resulting_text'], "Hello")
        # 6 insert events total = 6 total scored keystrokes
        self.assertEqual(result['total_scored_keystrokes'], 6)
        # 1 incorrect attempt ('x')
        self.assertEqual(result['incorrect_attempts'], 1)
        # 5 correct keystrokes
        self.assertEqual(result['correct_keystrokes'], 5)
        # 1 backspace
        self.assertEqual(result['backspace_count'], 1)

    def test_out_of_order_event_rejected(self):
        target = "Test"
        # Seq skips from 1 to 3
        events = [
            {"seq": 1, "type": "insert", "char": "T"},
            {"seq": 3, "type": "insert", "char": "e"},
        ]
        result = ScoringService.apply_events(target_text=target, events=events)
        self.assertFalse(result['success'])
        self.assertIn("Invalid event sequence", result['error'])

    def test_timed_competition_ranking_and_exact_tie(self):
        # Participants with identical WPM, accuracy, and incorrect attempts
        p1 = DummyAttempt('alice', wpm=80.0, accuracy=98.0, elapsed_seconds=60.0, incorrect_attempts=2)
        p2 = DummyAttempt('bob', wpm=80.0, accuracy=98.0, elapsed_seconds=60.0, incorrect_attempts=2)
        p3 = DummyAttempt('charlie', wpm=75.0, accuracy=95.0, elapsed_seconds=60.0, incorrect_attempts=4)

        ranked = ScoringService.rank_participants([p1, p2, p3], competition_format='timed', min_accuracy=80.0)

        # Alice and Bob should share Rank 1 as joint winners
        self.assertEqual(ranked[0]['rank'], 1)
        self.assertTrue(ranked[0]['is_winner'])
        self.assertEqual(ranked[1]['rank'], 1)
        self.assertTrue(ranked[1]['is_winner'])

        # Charlie should be Rank 3 (not 2)
        self.assertEqual(ranked[2]['rank'], 3)
        self.assertFalse(ranked[2]['is_winner'])

    def test_first_to_complete_ranking_and_min_accuracy(self):
        # First to complete requires passage completion + lowest server time
        p1 = DummyAttempt('speedy_but_inaccurate', wpm=100.0, accuracy=70.0, elapsed_seconds=20.0, incorrect_attempts=15, is_completed=True)
        p2 = DummyAttempt('clean_finisher', wpm=85.0, accuracy=98.0, elapsed_seconds=25.0, incorrect_attempts=1, is_completed=True)
        p3 = DummyAttempt('slower_finisher', wpm=70.0, accuracy=99.0, elapsed_seconds=30.0, incorrect_attempts=1, is_completed=True)
        p4 = DummyAttempt('did_not_finish', wpm=90.0, accuracy=99.0, elapsed_seconds=15.0, incorrect_attempts=0, is_completed=False)

        # Min accuracy threshold 85%
        ranked = ScoringService.rank_participants([p1, p2, p3, p4], competition_format='first_to_complete', min_accuracy=85.0)

        # p1 disqualified for accuracy < 85%, p4 disqualified for not completing
        # Eligible winners: p2 (25s) then p3 (30s)
        self.assertEqual(ranked[0]['attempt'].username, 'clean_finisher')
        self.assertEqual(ranked[0]['rank'], 1)
        self.assertTrue(ranked[0]['is_winner'])

        self.assertEqual(ranked[1]['attempt'].username, 'slower_finisher')
        self.assertEqual(ranked[1]['rank'], 2)

        # Ineligible participants should not receive winning rank
        ineligible_names = [r['attempt'].username for r in ranked if not r['is_eligible']]
        self.assertIn('speedy_but_inaccurate', ineligible_names)
        self.assertIn('did_not_finish', ineligible_names)

if __name__ == '__main__':
    unittest.main()


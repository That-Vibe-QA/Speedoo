from datetime import datetime, timezone
import math

class ScoringService:
    """
    Standardized, robust scoring engine for Speedoo.
    Scoring Rules:
    - WPM = (correctly typed characters / 5) / elapsed minutes.
    - Accuracy = correct keystrokes / total scored keystrokes * 100.
    - Backspace is a correction action, not a scored character keystroke.
    - Track incorrect attempts even if the user later corrects them.
    - Handle empty input, zero elapsed time, punctuation, spaces, and unfinished passages consistently.
    """

    @staticmethod
    def calculate_wpm(correct_chars: int, elapsed_seconds: float) -> float:
        if elapsed_seconds <= 0 or correct_chars <= 0:
            return 0.0
        elapsed_minutes = elapsed_seconds / 60.0
        words = correct_chars / 5.0
        wpm = words / elapsed_minutes
        # Return cleanly rounded to 1 decimal place or float
        return round(max(0.0, wpm), 1)

    @staticmethod
    def calculate_accuracy(correct_keystrokes: int, total_scored_keystrokes: int) -> float:
        if total_scored_keystrokes <= 0:
            return 100.0  # Neutral baseline when no scored keystrokes have occurred yet
        acc = (correct_keystrokes / total_scored_keystrokes) * 100.0
        return round(min(100.0, max(0.0, acc)), 1)

    @staticmethod
    def evaluate_typed_state(target_text: str, current_typed_text: str):
        """
        Calculates correct characters in the current prefix matching the target text.
        Also identifies current cursor position and whether exact match reached.
        """
        match_len = 0
        min_len = min(len(target_text), len(current_typed_text))
        for i in range(min_len):
            if target_text[i] == current_typed_text[i]:
                match_len += 1
            else:
                break
        
        is_exact_match = (current_typed_text == target_text)
        return {
            'correct_prefix_length': match_len,
            'is_exact_match': is_exact_match,
            'current_length': len(current_typed_text),
            'target_length': len(target_text)
        }

    @classmethod
    def apply_events(
        cls,
        target_text: str,
        events: list,
        existing_typed_text: str = "",
        existing_correct_keystrokes: int = 0,
        existing_total_scored_keystrokes: int = 0,
        existing_incorrect_attempts: int = 0,
        existing_backspace_count: int = 0,
        expected_seq_start: int = 1
    ):
        """
        Replays keystroke/edit events sequentially on the server.
        Event schema:
        {
          "seq": int (1-based strictly increasing),
          "type": "insert" | "backspace",
          "char": string (for insert),
          "client_t": float (optional monotonic ms)
        }
        
        Rules:
        - Out-of-order sequence numbers or gap in seq triggers validation error.
        - 'insert' adds char to typed string. It is a scored keystroke.
          If the added char matches target_text at that index, correct_keystrokes += 1.
          If not, incorrect_attempts += 1.
          total_scored_keystrokes += 1.
        - 'backspace' removes the last char from typed string (if not empty).
          Backspace is NOT a scored character keystroke and does NOT increment total_scored_keystrokes.
          backspace_count += 1.
        """
        typed = list(existing_typed_text)
        correct_ks = existing_correct_keystrokes
        total_ks = existing_total_scored_keystrokes
        incorrect = existing_incorrect_attempts
        backspaces = existing_backspace_count

        expected_seq = expected_seq_start
        suspicious_reasons = []

        for ev in events:
            seq = ev.get('seq')
            if seq != expected_seq:
                return {
                    'success': False,
                    'error': f'Invalid event sequence: expected {expected_seq}, got {seq}'
                }
            expected_seq += 1

            ev_type = ev.get('type')
            if ev_type == 'insert':
                char = ev.get('char', '')
                if len(char) != 1:
                    suspicious_reasons.append(f"Multi-character insertion detected: length {len(char)}")
                    # Multi-character pasted block
                    for c in char:
                        idx = len(typed)
                        total_ks += 1
                        if idx < len(target_text) and c == target_text[idx]:
                            correct_ks += 1
                        else:
                            incorrect += 1
                        typed.append(c)
                else:
                    idx = len(typed)
                    total_ks += 1
                    if idx < len(target_text) and char == target_text[idx]:
                        correct_ks += 1
                    else:
                        incorrect += 1
                    typed.append(char)

            elif ev_type == 'backspace':
                backspaces += 1
                if typed:
                    typed.pop()
            else:
                return {
                    'success': False,
                    'error': f'Unknown event type: {ev_type}'
                }

        resulting_text = "".join(typed)
        state = cls.evaluate_typed_state(target_text, resulting_text)

        return {
            'success': True,
            'resulting_text': resulting_text,
            'last_seq': expected_seq - 1,
            'correct_keystrokes': correct_ks,
            'total_scored_keystrokes': total_ks,
            'incorrect_attempts': incorrect,
            'backspace_count': backspaces,
            'correct_prefix_length': state['correct_prefix_length'],
            'is_exact_match': state['is_exact_match'],
            'suspicious': len(suspicious_reasons) > 0,
            'suspicious_reasons': suspicious_reasons
        }

    @classmethod
    def rank_participants(cls, attempts: list, competition_format: str, min_accuracy: float = 0.0):
        """
        Rank participants based on competition format with tie-breaking rules.
        
        Format 1: 'timed'
        Eligible participants: accuracy >= min_accuracy.
        Primary: Highest WPM (descending)
        Secondary: Highest Accuracy (descending)
        Tertiary: Fewer incorrect attempts (ascending)
        Quaternary: Earlier attempt finish/start time (ascending)

        Format 2: 'first_to_complete'
        Eligible participants: is_completed is True (exact passage match) and accuracy >= min_accuracy.
        Primary: Lowest server-measured completion time (elapsed_seconds ascending)
        Secondary: Highest Accuracy (descending)
        Tertiary: Fewer incorrect attempts (ascending)
        Quaternary: Higher WPM (descending)

        Tie handling:
        For exact ties on primary, secondary, and tertiary criteria, assign shared rank (e.g. 1, 1, 3).
        Never select winner randomly.
        """
        # Separate eligible vs ineligible
        eligible = []
        ineligible = []

        for att in attempts:
            meets_acc = (att.accuracy >= min_accuracy)
            if competition_format == 'first_to_complete':
                is_finisher = att.is_completed and att.status == 'completed'
                if is_finisher and meets_acc:
                    eligible.append(att)
                else:
                    ineligible.append(att)
            else:  # timed
                if meets_acc and (att.status in ('completed', 'in_progress')):
                    eligible.append(att)
                else:
                    ineligible.append(att)

        if competition_format == 'first_to_complete':
            def sort_key(att):
                # Elapsed time ascending, Accuracy descending, incorrect ascending
                return (
                    round(att.elapsed_seconds, 2),
                    -round(att.accuracy, 2),
                    att.incorrect_attempts
                )
            eligible.sort(key=sort_key)
        else:  # timed
            def sort_key(att):
                # WPM descending, Accuracy descending, incorrect ascending
                return (
                    -round(att.wpm, 2),
                    -round(att.accuracy, 2),
                    att.incorrect_attempts
                )
            eligible.sort(key=sort_key)

        # Assign ranks with shared ties
        ranked_results = []
        current_rank = 1
        for i, att in enumerate(eligible):
            if i > 0:
                prev = eligible[i - 1]
                if competition_format == 'first_to_complete':
                    is_tie = (
                        round(att.elapsed_seconds, 2) == round(prev.elapsed_seconds, 2) and
                        round(att.accuracy, 2) == round(prev.accuracy, 2) and
                        att.incorrect_attempts == prev.incorrect_attempts
                    )
                else:
                    is_tie = (
                        round(att.wpm, 2) == round(prev.wpm, 2) and
                        round(att.accuracy, 2) == round(prev.accuracy, 2) and
                        att.incorrect_attempts == prev.incorrect_attempts
                    )
                if is_tie:
                    rank_to_assign = ranked_results[i - 1]['rank']
                else:
                    rank_to_assign = i + 1
            else:
                rank_to_assign = 1

            ranked_results.append({
                'attempt': att,
                'rank': rank_to_assign,
                'is_eligible': True,
                'is_winner': rank_to_assign == 1
            })

        # Append ineligible participants at the end without a winning rank
        for att in ineligible:
            ranked_results.append({
                'attempt': att,
                'rank': None,
                'is_eligible': False,
                'is_winner': False
            })

        return ranked_results


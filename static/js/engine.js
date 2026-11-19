/**
 * Speedoo Client Core Engine
 * Manages monotonic clock, event queueing, keyboard capturing,
 * rendering accessible character states, and server synchronization.
 */
class SpeedooEngine {
  constructor(options = {}) {
    this.targetText = options.targetText || "";
    this.mode = options.mode || "timed"; // "timed" or "completion"
    this.durationSeconds = options.durationSeconds || 60;
    this.attemptId = options.attemptId || null;
    this.syncUrl = options.syncUrl || null;
    this.onTick = options.onTick || null;
    this.onFinish = options.onFinish || null;
    this.isCompetition = options.isCompetition || false;

    // State
    this.typedChars = [];
    this.eventsQueue = [];
    this.nextSeq = 1;
    this.hasStarted = false;
    this.isFinished = false;
    this.isSyncing = false;

    // Timing with monotonic clock
    this.startTimeMonotonic = null;
    this.timerInterval = null;
    this.syncInterval = null;
    this.elapsedSeconds = 0;
    this.remainingSeconds = this.durationSeconds;

    // Metrics
    this.correctKeystrokes = 0;
    this.totalScoredKeystrokes = 0;
    this.incorrectAttempts = 0;
    this.backspaces = 0;
    this.wpm = 0.0;
    this.accuracy = 100.0;

    // Track detailed mistake logs: { index, expected, typed, word }
    this.mistakesLog = [];
  }

  setTargetText(text) {
    this.targetText = text || "";
    this.renderText();
  }

  setAttempt(attemptId, syncUrl, targetText, duration, mode) {
    this.attemptId = attemptId;
    this.syncUrl = syncUrl;
    if (targetText) this.targetText = targetText;
    if (duration !== undefined) this.durationSeconds = duration;
    if (mode) this.mode = mode;
    this.renderText();
  }

  restoreState(typedText, lastSeq, wpm, accuracy, elapsedSeconds) {
    this.typedChars = typedText ? typedText.split('') : [];
    this.nextSeq = (lastSeq || 0) + 1;
    this.wpm = wpm || 0.0;
    this.accuracy = accuracy || 100.0;
    this.elapsedSeconds = elapsedSeconds || 0.0;
    this.hasStarted = true;
    this.renderText();
    this.startLocalTimer();
  }

  startLocalTimer() {
    if (this.timerInterval) return;
    this.startTimeMonotonic = performance.now() - (this.elapsedSeconds * 1000);

    this.timerInterval = setInterval(() => {
      if (this.isFinished) return;
      const now = performance.now();
      this.elapsedSeconds = Math.max(0.001, (now - this.startTimeMonotonic) / 1000.0);

      if (this.mode === 'timed' && this.durationSeconds) {
        this.remainingSeconds = Math.max(0, this.durationSeconds - this.elapsedSeconds);
        if (this.remainingSeconds <= 0) {
          this.remainingSeconds = 0;
          this.finish();
          return;
        }
      }

      this.computeMetrics();
      if (this.onTick) {
        this.onTick({
          elapsed: this.elapsedSeconds,
          remaining: this.remainingSeconds,
          wpm: this.wpm,
          accuracy: this.accuracy,
          progress: this.computeProgress()
        });
      }
    }, 100);

    // Periodically flush events to server (every 500ms)
    this.syncInterval = setInterval(() => {
      this.flushEvents();
    }, 500);
  }

  handleKeyDown(e) {
    if (this.isFinished) return;

    // Disallow modifiers
    if (e.ctrlKey || e.metaKey || e.altKey) {
      if (e.key === 'v' || e.key === 'V') {
        e.preventDefault(); // Extra defense against paste shortcuts
      }
      return;
    }

    if (e.key === 'Backspace') {
      e.preventDefault();
      if (!this.hasStarted) return;
      this.backspaces += 1;
      if (this.typedChars.length > 0) {
        this.typedChars.pop();
        this.eventsQueue.push({
          seq: this.nextSeq++,
          type: 'backspace',
          client_t: performance.now()
        });
        this.computeMetrics();
        this.renderText();
      }
      return;
    }

    // Single character typing
    if (e.key.length === 1) {
      e.preventDefault();

      if (!this.hasStarted) {
        this.hasStarted = true;
        this.startLocalTimer();
      }

      const char = e.key;
      const targetChar = this.targetText[this.typedChars.length];
      
      this.totalScoredKeystrokes += 1;
      const curIndex = this.typedChars.length;
      if (char === targetChar) {
        this.correctKeystrokes += 1;
      } else {
        this.incorrectAttempts += 1;
        // Record mistake details with surrounding context word
        this.recordMistake(curIndex, targetChar, char);
      }

      this.typedChars.push(char);
      this.eventsQueue.push({
        seq: this.nextSeq++,
        type: 'insert',
        char: char,
        client_t: performance.now()
      });

      this.computeMetrics();
      this.renderText();

      // Check if user has finished the entire text (both timed and completion modes)
      if (this.typedChars.join('') === this.targetText) {
        this.finish();
      }
    }
  }

  recordMistake(index, expected, typed) {
    let wordStart = index;
    while (wordStart > 0 && this.targetText[wordStart - 1] !== ' ') {
      wordStart--;
    }
    let wordEnd = index;
    while (wordEnd < this.targetText.length && this.targetText[wordEnd] !== ' ') {
      wordEnd++;
    }
    const contextWord = this.targetText.substring(wordStart, wordEnd) || '(space)';

    this.mistakesLog.push({
      index: index,
      expected: expected === ' ' ? '(space)' : expected,
      typed: typed === ' ' ? '(space)' : typed,
      word: contextWord
    });
  }

  computeMetrics() {
    // Correct prefix length
    let correctPrefix = 0;
    const minLen = Math.min(this.targetText.length, this.typedChars.length);
    for (let i = 0; i < minLen; i++) {
      if (this.targetText[i] === this.typedChars[i]) {
        correctPrefix++;
      } else {
        break;
      }
    }

    // WPM = (correctly typed characters / 5) / elapsed minutes
    if (this.elapsedSeconds > 0) {
      const minutes = this.elapsedSeconds / 60.0;
      this.wpm = Math.max(0, Math.round(((correctPrefix / 5.0) / minutes) * 10) / 10);
    } else {
      this.wpm = 0.0;
    }

    // Accuracy = correct keystrokes / total scored keystrokes * 100
    if (this.totalScoredKeystrokes > 0) {
      const acc = (this.correctKeystrokes / this.totalScoredKeystrokes) * 100.0;
      this.accuracy = Math.round(Math.min(100.0, Math.max(0.0, acc)) * 10) / 10;
    } else {
      this.accuracy = 100.0;
    }
  }

  computeProgress() {
    if (!this.targetText || this.targetText.length === 0) return 0;
    return Math.min(100, Math.round((this.typedChars.length / this.targetText.length) * 100));
  }

  renderText() {
    const container = document.getElementById('typingDisplay');
    if (!container) return;

    const target = this.targetText;
    const typed = this.typedChars;
    const cursorIdx = typed.length;

    let html = '';
    const total = target.length;

    for (let i = 0; i < total; i++) {
      const char = target[i];
      let displayChar = char;
      if (char === ' ') {
        displayChar = '&nbsp;';
      }

      if (i < typed.length) {
        if (typed[i] === char) {
          html += `<span class="char-correct">${displayChar}</span>`;
        } else {
          // If typed incorrectly, show what was actually typed or an error marker
          const typedChar = typed[i] === ' ' ? '&nbsp;' : typed[i];
          html += `<span class="char-incorrect" title="Expected '${char}'">${typedChar}</span>`;
        }
      } else if (i === cursorIdx) {
        html += `<span class="char-cursor">${displayChar}</span>`;
      } else {
        html += `<span class="char-pending">${displayChar}</span>`;
      }
    }

    container.innerHTML = html;
  }

  async flushEvents(force = false) {
    if (!this.syncUrl || !this.attemptId) return;
    if (this.eventsQueue.length === 0 && !force) return;
    if (this.isSyncing && !force) return;

    this.isSyncing = true;
    const batch = [...this.eventsQueue];

    try {
      const response = await fetch(this.syncUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ events: batch })
      });

      if (response.ok) {
        const data = await response.json();
        // Remove successfully flushed events
        this.eventsQueue.splice(0, batch.length);

        if (data.is_finished) {
          this.wpm = data.wpm;
          this.accuracy = data.accuracy;
          this.elapsedSeconds = data.elapsed_seconds;
          this.finish(true);
        }
      }
    } catch (err) {
      console.warn("Event sync queued, will retry on next tick:", err);
    } finally {
      this.isSyncing = false;
    }
  }

  async finish(fromServer = false) {
    if (this.isFinished) return;
    this.isFinished = true;

    if (this.timerInterval) clearInterval(this.timerInterval);
    if (this.syncInterval) clearInterval(this.syncInterval);

    // Final event flush
    await this.flushEvents(true);

    if (this.onFinish) {
      this.onFinish({
        wpm: this.wpm,
        accuracy: this.accuracy,
        elapsedSeconds: this.elapsedSeconds,
        incorrectAttempts: this.incorrectAttempts,
        backspaces: this.backspaces,
        correctChars: this.correctKeystrokes,
        mistakesLog: this.mistakesLog,
        targetText: this.targetText
      });
    }
  }
}


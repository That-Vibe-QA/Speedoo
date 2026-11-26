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

  clearTypedWordsKeepTimer() {
    if (!this.hasStarted || this.isFinished) return;

    // Send backspaces to roll back typed buffer on server or record a reset
    const rollbackCount = this.typedChars.length;
    for (let i = 0; i < rollbackCount; i++) {
      this.eventsQueue.push({
        seq: this.nextSeq++,
        type: 'backspace',
        client_t: performance.now()
      });
    }

    this.typedChars = [];
    this.correctKeystrokes = 0;
    this.computeMetrics();
    this.renderText();
    this.flushEvents();
  }

  playKeySound(type = 'key') {
    if (window.speedooSoundEnabled === false) return;
    try {
      if (!this._audioCtx) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        this._audioCtx = new AudioCtx();
      }
      if (this._audioCtx.state === 'suspended') {
        this._audioCtx.resume();
      }
      const ctx = this._audioCtx;
      const now = ctx.currentTime;

      // Lazily create a reusable short white-noise buffer for realistic switch click
      if (!this._noiseBuffer) {
        const bufferSize = Math.floor(ctx.sampleRate * 0.04);
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * Math.exp(-i / (bufferSize * 0.25));
        }
        this._noiseBuffer = buffer;
      }

      // 1. Crisp mechanical switch click (filtered noise burst)
      const noise = ctx.createBufferSource();
      noise.buffer = this._noiseBuffer;

      const filter = ctx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.frequency.setValueAtTime(
        type === 'error' ? 900 : (type === 'space' || type === 'backspace' ? 1600 : 2800 + Math.random() * 500),
        now
      );
      filter.Q.setValueAtTime(type === 'error' ? 1.5 : 2.2, now);

      const noiseGain = ctx.createGain();
      noiseGain.gain.setValueAtTime(type === 'error' ? 0.14 : 0.22, now);
      noiseGain.gain.exponentialRampToValueAtTime(0.001, now + 0.025);

      noise.connect(filter);
      filter.connect(noiseGain);
      noiseGain.connect(ctx.destination);
      noise.start(now);
      noise.stop(now + 0.03);

      // 2. Subtle keycap bottom-out thock (short low-end impulse)
      const thock = ctx.createOscillator();
      const thockGain = ctx.createGain();
      thock.type = 'sine';
      const baseFreq = type === 'error' ? 95 : (type === 'space' || type === 'backspace' ? 115 : 155 + Math.random() * 20);
      thock.frequency.setValueAtTime(baseFreq, now);
      thock.frequency.exponentialRampToValueAtTime(45, now + 0.022);
      thockGain.gain.setValueAtTime(type === 'error' ? 0.12 : 0.08, now);
      thockGain.gain.exponentialRampToValueAtTime(0.001, now + 0.024);

      thock.connect(thockGain);
      thockGain.connect(ctx.destination);
      thock.start(now);
      thock.stop(now + 0.025);
    } catch (e) {
      // Ignore audio errors if blocked by browser autoplay policy
    }
  }

  handleKeyDown(e) {
    if (this.isFinished) return;

    // Ctrl+Backspace / Alt+Backspace / Cmd+Backspace: delete whole current word
    if (e.key === 'Backspace' && (e.ctrlKey || e.metaKey || e.altKey)) {
      e.preventDefault();
      if (!this.hasStarted || this.typedChars.length === 0) return;
      this.playKeySound('backspace');
      // Skip any trailing spaces first, then delete back to the previous space
      while (this.typedChars.length > 0 && this.typedChars[this.typedChars.length - 1] === ' ') {
        this.typedChars.pop();
        this.backspaces += 1;
        this.eventsQueue.push({ seq: this.nextSeq++, type: 'backspace', client_t: performance.now() });
      }
      while (this.typedChars.length > 0 && this.typedChars[this.typedChars.length - 1] !== ' ') {
        this.typedChars.pop();
        this.backspaces += 1;
        this.eventsQueue.push({ seq: this.nextSeq++, type: 'backspace', client_t: performance.now() });
      }
      this.computeMetrics();
      this.renderText();
      return;
    }

    // Disallow modifiers (except Shift, AltGraph for international keyboards)
    if (e.ctrlKey || e.metaKey) {
      if (e.key === 'v' || e.key === 'V') {
        e.preventDefault(); // Extra defense against paste shortcuts
      }
      return;
    }

    if (e.key === 'Backspace') {
      e.preventDefault();
      if (!this.hasStarted) return;
      this.playKeySound('backspace');
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

    // Capture input (single character or multi-byte Unicode/composition char)
    // Ignore modifier/navigation/non-character keys (e.g., CapsLock, Insert, ArrowLeft, F1-F12)
    // Allow single-character keys (including Unicode/combining characters where Array.from(e.key).length === 1)
    if (e.key && Array.from(e.key.normalize('NFC')).length === 1) {
      e.preventDefault();

      if (!this.hasStarted) {
        this.hasStarted = true;
        this.startLocalTimer();
      }

      const inputChars = Array.from(e.key.normalize('NFC'));
      for (const char of inputChars) {
        const curIndex = this.typedChars.length;
        const targetChar = this.targetText[curIndex];
        
        this.totalScoredKeystrokes += 1;
        if (char === targetChar) {
          this.correctKeystrokes += 1;
          this.playKeySound(char === ' ' ? 'space' : 'key');
        } else {
          this.incorrectAttempts += 1;
          this.playKeySound('error');
          this.recordMistake(curIndex, targetChar, char);
        }

        this.typedChars.push(char);
        this.eventsQueue.push({
          seq: this.nextSeq++,
          type: 'insert',
          char: char,
          client_t: performance.now()
        });
      }

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
    if (fromServer && this.mode === 'timed' && this.remainingSeconds > 0) {
      this.remainingSeconds = 0;
      if (this.onTick) {
        this.onTick({
          elapsed: this.elapsedSeconds,
          remaining: 0,
          mode: this.mode
        });
      }
    }

    if (this.timerInterval) clearInterval(this.timerInterval);
    if (this.syncInterval) clearInterval(this.syncInterval);

    // Final event flush
    await this.flushEvents(true);

    if (this.onFinish) {
      const isCompleted = (this.typedChars.join('') === this.targetText);
      this.onFinish({
        wpm: this.wpm,
        accuracy: this.accuracy,
        elapsedSeconds: this.elapsedSeconds,
        incorrectAttempts: this.incorrectAttempts,
        backspaces: this.backspaces,
        correctChars: this.correctKeystrokes,
        mistakesLog: this.mistakesLog,
        targetText: this.targetText,
        isCompleted: isCompleted,
        typedLength: this.typedChars.length,
        totalLength: this.targetText.length
      });
    }
  }
}


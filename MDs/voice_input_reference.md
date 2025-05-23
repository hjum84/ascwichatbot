# Voice Input and Speech Recognition Reference Guide

## Web Speech API Overview

The Web Speech API provides two main functionalities:
- **SpeechRecognition**: Converts speech to text
- **SpeechSynthesis**: Converts text to speech (text-to-speech or TTS)

This guide focuses on the Speech Recognition functionality.

## Core Components

### Key Objects and Variables

| Variable | Type | Purpose |
|----------|------|---------|
| `recognition` | Object | Main SpeechRecognition instance |
| `isListening` | Boolean | Tracks if recording is active |
| `appendedTranscript` | String | Stores accumulated speech text |
| `micBtn` | DOM Element | The microphone button in the UI |
| `userInput` | DOM Element | The text area where transcribed text appears |

### SpeechRecognition Configuration

```javascript
// Initialize recognition object
recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();

// Configure key properties
recognition.continuous = true;      // Don't stop after silence
recognition.interimResults = true;  // Get real-time results
recognition.lang = "en-US";         // Set recognition language
```

## Event Handlers

### 1. Button Click Handler

This handler toggles speech recognition on/off:

```javascript
micBtn.addEventListener("click", function() {
    if (isListening) {
        // Stop recording
        recognition.stop();
        isListening = false;
        micBtn.classList.remove("active");
    } else {
        try {
            // Save current text to prevent deleted text from reappearing
            appendedTranscript = userInput.value;
            
            // Start recording
            recognition.start();
            isListening = true;
            micBtn.classList.add("active");
            userInput.focus();
        } catch (error) {
            console.error("Speech recognition error:", error);
            alert("Could not start speech recognition. Please check your browser settings.");
        }
    }
});
```

### 2. Result Handler

Processes speech recognition results as they arrive:

```javascript
recognition.onresult = function(event) {
    // Extract transcript from results
    const transcript = Array.from(event.results)
        .map(result => result[0])
        .map(result => result.transcript)
        .join("");
    
    // Process transcript with text enhancements
    const processedTranscript = autoCapitalizeSentences(replaceSpokenPunctuation(transcript));
    
    // Update textarea with processed text
    if (appendedTranscript) {
        userInput.value = appendedTranscript + " " + processedTranscript;
    } else {
        userInput.value = processedTranscript;
    }
    
    // Auto-resize textarea
    userInput.style.height = "auto";
    userInput.style.height = userInput.scrollHeight + "px";
};
```

### 3. End Handler

Manages what happens when speech recognition session ends:

```javascript
recognition.onend = function() {
    if (!isListening) {
        // If we manually stopped, save the current text
        if (userInput.value) {
            appendedTranscript = userInput.value;
        }
        micBtn.classList.remove("active");
    } else {
        // If it ended but we want to keep listening, restart
        try {
            recognition.start();
        } catch (error) {
            console.error("Error restarting recognition:", error);
        }
    }
};
```

### 4. Error Handler

Manages recognition errors:

```javascript
recognition.onerror = function(event) {
    console.error("Speech recognition error:", event.error);
    isListening = false;
    micBtn.classList.remove("active");
    
    if (event.error === "not-allowed") {
        alert("Microphone access is required. Please allow microphone access in your browser settings.");
    }
};
```

## Text Processing Utilities

### Automatic Punctuation Replacement

Converts spoken punctuation words into actual punctuation symbols:

```javascript
function replaceSpokenPunctuation(text) {
  return text
    .replace(/\s*\bperiod\b\s*/gi, ". ")
    .replace(/\s*\bcomma\b\s*/gi, ", ")
    .replace(/\s*\bexclamation (point|mark)\b\s*/gi, "! ")
    .replace(/\s*\bquestion mark\b\s*/gi, "? ")
    .replace(/\s*\bcolon\b\s*/gi, ": ")
    .replace(/\s*\bsemicolon\b\s*/gi, "; ")
    .replace(/\s*\bdash\b\s*/gi, "-")
    .replace(/\s*\bopen parenthesis\b\s*/gi, " (")
    .replace(/\s*\bclose parenthesis\b\s*/gi, ") ");
}
```

### Automatic Capitalization

Capitalizes the first letter of sentences:

```javascript
function autoCapitalizeSentences(text) {
  // Capitalize the first letter of the text and after punctuation
  return text.replace(/(^\s*\w|[.!?]\s*\w)/g, function(match) {
    return match.toUpperCase();
  });
}
```

## Language Support

The Speech Recognition API supports many languages. Set the language using the `lang` property:

```javascript
// Korean
recognition.lang = "ko-KR";

// English (US)
recognition.lang = "en-US";

// English (UK) 
recognition.lang = "en-GB";

// Chinese (Simplified)
recognition.lang = "zh-CN";

// Chinese (Traditional, Taiwan)
recognition.lang = "zh-TW";

// Japanese
recognition.lang = "ja-JP";

// French
recognition.lang = "fr-FR";

// German
recognition.lang = "de-DE";

// Spanish
recognition.lang = "es-ES";
```

## Common Issues & Solutions

### 1. Previous Deleted Text Reappears

**Problem**: When stopping speech recognition, editing the text, and starting again, the deleted text reappears.

**Solution**: Update `appendedTranscript` with the current input value before starting recognition:

```javascript
appendedTranscript = userInput.value;
```

### 2. Recognition Stops Unexpectedly

**Problem**: Speech recognition stops after short pauses.

**Solution**: Ensure `continuous` is set to true and handle reconnection in the `onend` event:

```javascript
recognition.continuous = true;

recognition.onend = function() {
    if (isListening) {
        try {
            recognition.start();
        } catch (error) {
            console.error("Error restarting recognition:", error);
        }
    }
};
```

### 3. Poor Recognition Accuracy

**Solutions**:
- Ensure you're using the correct language setting
- Speak clearly and at a moderate pace
- Minimize background noise
- Use a good quality microphone

### 4. Browser Compatibility

Speech Recognition is supported in:
- Chrome
- Edge
- Safari (newer versions)
- Firefox (requires enabling flags)

Always check for browser support:

```javascript
if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
    // Speech recognition supported
} else {
    // Not supported - show fallback UI
}
```

## UI Implementation

### 1. Microphone Button

```html
<button id="micBtn" class="mic-btn" type="button" aria-label="Start voice input">
  <span class="mic-wave"></span>
  <svg viewBox="0 0 24 24" fill="none">
    <path d="M12 14c1.66 0 3-1.34 3-3V5a3 3 0 0 0-6 0v6c0 1.66 1.34 3 3 3zm-1-9a1 1 0 0 1 2 0v6a1 1 0 0 1-2 0V5z" fill="currentColor"/>
    <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" fill="currentColor"/>
  </svg>
</button>
```

### 2. Microphone Button Styling

```css
.mic-btn {
  background: #fff;
  border: none;
  border-radius: 50%;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: box-shadow 0.2s, background 0.2s;
  margin-right: 8px;
  cursor: pointer;
  outline: none;
  position: relative;
}

.mic-btn.active {
  background: #ff4d4f;
  box-shadow: 0 0 0 6px rgba(255,77,79,0.15);
}

.mic-btn .mic-wave {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(255,77,79,0.12);
  opacity: 0;
  transition: opacity 0.2s;
  z-index: 0;
}

.mic-btn.active .mic-wave {
  opacity: 1;
  animation: mic-wave-pulse 1.2s infinite;
}

@keyframes mic-wave-pulse {
  0% { transform: translate(-50%, -50%) scale(1); opacity: 0.7; }
  70% { transform: translate(-50%, -50%) scale(1.4); opacity: 0.2; }
  100% { transform: translate(-50%, -50%) scale(1.7); opacity: 0; }
}
```

## Advanced Features

### Adding Custom Commands

You can implement custom command recognition by analyzing the transcribed text:

```javascript
recognition.onresult = function(event) {
    // Get transcript
    const transcript = Array.from(event.results)
        .map(result => result[0])
        .map(result => result.transcript)
        .join("");
    
    // Check for commands
    const lowercaseTranscript = transcript.toLowerCase();
    
    if (lowercaseTranscript.includes("clear all")) {
        // Clear the input
        userInput.value = "";
        appendedTranscript = "";
        return;
    }
    
    if (lowercaseTranscript.includes("send message")) {
        // Send the current message
        sendMessage();
        return;
    }
    
    // Continue with normal processing
    // ...
};
```

### Multiple Language Support

For applications supporting multiple languages, create a language selector:

```javascript
// Language selector
const languageSelect = document.getElementById("languageSelect");
languageSelect.addEventListener("change", function() {
    recognition.lang = this.value;
    
    // Restart recognition if already listening
    if (isListening) {
        recognition.stop();
        recognition.start();
    }
});
```

## Resources

- [MDN Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)
- [Web Speech API Specification](https://wicg.github.io/speech-api/)
- [Browser Compatibility](https://caniuse.com/?search=speech%20recognition)
- [List of Language Codes](https://www.w3schools.com/tags/ref_language_codes.asp)

## Robust Solution: Preventing Deleted Text Reappearing and Repeated Transcripts

### Problem 1: Deleted Text Reappears After Voice Input Restart

**Description:**
When the user deletes or edits the input text and restarts voice input, previously deleted text may reappear. This happens if the speech recognition buffer (e.g., `appendedTranscript`) is not properly synchronized with the current input value.

**Solution:**
Always use the current value of the input field as the base for new speech recognition results. If the user edits or deletes text, the buffer should be updated immediately. When speech recognition starts, save the current input value as the base.

### Problem 2: Repeated/Triplicated Transcripts

**Description:**
Sometimes, the same spoken phrase appears multiple times in the input. This is caused by naively concatenating interim and final transcripts, so that when a final result is received, the same text is appended again.

**Solution:**
- Only show the interim transcript as a temporary addition to the input.
- When a final transcript is received, append it to the base and clear the interim.
- The input should always be: `base input at recognition start` + `all final transcripts` + `current interim transcript`.

### Safe Implementation Pattern (in English)

```javascript
let recognitionBase = ""; // The input value when speech recognition starts
let recognitionFinal = ""; // Accumulated final transcript

micBtn.addEventListener("click", function() {
    if (isListening) {
        recognition.stop();
        isListening = false;
        micBtn.classList.remove("active");
    } else {
        try {
            recognitionBase = userInput.value; // Save input value at recognition start
            recognitionFinal = "";
            recognition.start();
            isListening = true;
            micBtn.classList.add("active");
            userInput.focus();
        } catch (error) {
            console.error("Speech recognition error:", error);
            alert("Could not start speech recognition. Please check your browser settings.");
        }
    }
});

recognition.onresult = function(event) {
    let interimTranscript = "";
    for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
            recognitionFinal += event.results[i][0].transcript;
        } else {
            interimTranscript += event.results[i][0].transcript;
        }
    }
    // Process transcripts
    let finalText = autoCapitalizeSentences(replaceSpokenPunctuation(recognitionFinal));
    let interimText = autoCapitalizeSentences(replaceSpokenPunctuation(interimTranscript));
    userInput.value = recognitionBase + finalText + interimText;
    userInput.style.height = "auto";
    userInput.style.height = userInput.scrollHeight + "px";
};

userInput.addEventListener('input', function() {
    recognitionBase = this.value; // Sync base with current input on user edit
    recognitionFinal = ""; // Reset accumulated transcript on manual edit
    this.style.height = 'auto';
    this.style.height = this.scrollHeight + 'px';
    scrollToBottom();
});
```

**Key Points:**
- The input field always reflects the current state: base + all final transcripts + current interim transcript.
- If the user edits or deletes text, the base and final transcript are reset, so deleted text never reappears.
- Interim results are only shown temporarily and do not cause duplication when final results arrive.

This approach fully solves both the deleted text reappearing and repeated transcript issues in voice input UX. 
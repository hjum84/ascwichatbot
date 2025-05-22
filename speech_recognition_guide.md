# Speech Recognition Troubleshooting Guide

## Core Speech Recognition Variables

- `recognition`: The SpeechRecognition object (or webkitSpeechRecognition for Chrome)
- `isListening`: Boolean flag to track if recording is active
- `appendedTranscript`: Stores the accumulated speech recognition text

## Important Event Handlers

### Button Click Handler
```javascript
micBtn.addEventListener("click", function() {
    if (isListening) {
        // Stop recording
        recognition.stop();
        isListening = false;
        micBtn.classList.remove("active");
    } else {
        try {
            // Update appendedTranscript to current input value 
            // This ensures manually deleted text doesn't reappear
            appendedTranscript = userInput.value;
            
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

### Result Handler
```javascript
recognition.onresult = function(event) {
    const transcript = Array.from(event.results)
        .map(result => result[0])
        .map(result => result.transcript)
        .join("");
    
    // Process transcript with custom functions
    const processedTranscript = autoCapitalizeSentences(replaceSpokenPunctuation(transcript));
    
    // Append to existing text instead of replacing
    if (appendedTranscript) {
        userInput.value = appendedTranscript + " " + processedTranscript;
    } else {
        userInput.value = processedTranscript;
    }
    
    userInput.style.height = "auto";
    userInput.style.height = userInput.scrollHeight + "px";
};
```

### End Handler
```javascript
recognition.onend = function() {
    // Only save transcript if we're actually stopping (not just pausing)
    if (!isListening) {
        if (userInput.value) {
            appendedTranscript = userInput.value;
        }
        micBtn.classList.remove("active");
    } else {
        // If we're still supposed to be listening, restart recognition
        try {
            recognition.start();
        } catch (error) {
            console.error("Error restarting recognition:", error);
        }
    }
};
```

### Error Handler
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

## Speech Recognition Configuration

```javascript
recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
recognition.continuous = true;  // Keep recording even during pauses
recognition.interimResults = true;  // Get results as they're recognized
recognition.lang = "en-US";  // Set language - can be changed for different languages
```

## Common Issues and Fixes

### 1. Text Disappears When Stopping and Restarting Recognition
**Solution**: When starting recognition, save the current input value to `appendedTranscript`:
```javascript
appendedTranscript = userInput.value;
```

### 2. Previous Deleted Text Reappears
**Solution**: Update `appendedTranscript` before starting new recognition:
```javascript
appendedTranscript = userInput.value;
```

### 3. Language Recognition Issues
**Solution**: Change the language setting:
```javascript
recognition.lang = "ko-KR";  // Korean
recognition.lang = "en-US";  // English (US)
recognition.lang = "ja-JP";  // Japanese
recognition.lang = "zh-CN";  // Chinese (Simplified)
```

### 4. Browser Compatibility
Speech Recognition works in:
- Chrome
- Edge
- Safari (newer versions)
- Firefox (with flag enabled)

Always check for browser support:
```javascript
if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
    // Speech recognition supported
} else {
    // Not supported - show fallback UI
}
```

### 5. Recognition Stopping Unexpectedly
**Solution**: Check for errors in the console, and ensure `continuous` is set to true.

## Text Processing Helpers

### Auto-Capitalize Sentences
```javascript
function autoCapitalizeSentences(text) {
  return text.replace(/(^\s*\w|[.!?]\s*\w)/g, function(match) {
    return match.toUpperCase();
  });
}
```

### Replace Spoken Punctuation
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

## Using Different Languages

To change the recognition language, modify `recognition.lang`:

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
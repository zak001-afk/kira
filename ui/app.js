// ═══════════════════════════════════════════════════════════════
// KIRA 3D Neural Interface - Application Logic
// ═══════════════════════════════════════════════════════════════

const API_BASE = 'http://localhost:8765';
let currentAudio = null;
let isMuted = false;

// ═══════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  initClock();
  initEventListeners();
  startSystemMonitoring();
  updateTasks();
  
  // Set boot time
  const bootTime = document.getElementById('boot-time');
  if (bootTime) {
    bootTime.textContent = new Date().toLocaleTimeString('en-US', { 
      hour12: false, 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit' 
    });
  }
  
  console.log('[KIRA] 3D Neural Interface initialized');
});

// ═══════════════════════════════════════════════════════════════
// Clock
// ═══════════════════════════════════════════════════════════════

function initClock() {
  function updateClock() {
    const now = new Date();
    const timeEl = document.getElementById('time');
    const dateEl = document.getElementById('date');
    
    if (timeEl) {
      timeEl.textContent = now.toLocaleTimeString('en-US', { hour12: false });
    }
    
    if (dateEl) {
      dateEl.textContent = now.toLocaleDateString('en-US', { 
        weekday: 'short', 
        month: 'short', 
        day: 'numeric',
        year: 'numeric'
      });
    }
  }
  
  updateClock();
  setInterval(updateClock, 1000);
}

// ═══════════════════════════════════════════════════════════════
// Event Listeners
// ═══════════════════════════════════════════════════════════════

function initEventListeners() {
  // Send button
  const sendBtn = document.getElementById('send');
  if (sendBtn) {
    sendBtn.addEventListener('click', sendCommand);
  }
  
  // Enter key
  const commandInput = document.getElementById('command');
  if (commandInput) {
    commandInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        sendCommand();
      }
    });
  }
  
  // Clear chat
  const clearBtn = document.getElementById('clear-chat');
  if (clearBtn) {
    clearBtn.addEventListener('click', clearConversation);
  }
  
  // Mute button
  const muteBtn = document.getElementById('mute');
  if (muteBtn) {
    muteBtn.addEventListener('click', toggleMute);
  }
  
  // Microphone button
  const micBtn = document.getElementById('mic');
  if (micBtn) {
    micBtn.addEventListener('click', toggleVoiceInput);
  }
}

// ═══════════════════════════════════════════════════════════════
// Command Processing
// ═══════════════════════════════════════════════════════════════

async function sendCommand() {
  const input = document.getElementById('command');
  const text = input.value.trim();
  
  if (!text) return;
  
  addMessage('USER', text, true);
  input.value = '';
  
  setActivity('thinking');
  
  try {
    const response = await fetch(`${API_BASE}/api/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    
    const data = await response.json();
    
    if (data.error) {
      addMessage('KIRA', `Error: ${data.error}`);
    } else if (data.response) {
      addMessage('KIRA', data.response);
      if (!isMuted) {
        speakText(data.response);
      }
    } else if (data.action) {
      addMessage('KIRA', `Action executed: ${data.action}`);
    }
    
    setActivity('active');
    
    // Refresh tasks if needed
    if (text.toLowerCase().includes('task') || text.toLowerCase().includes('remind')) {
      setTimeout(updateTasks, 500);
    }
    
  } catch (error) {
    console.error('[KIRA] Command error:', error);
    addMessage('KIRA', 'I apologize, sir. I encountered an error processing your request.');
    setActivity('active');
  }
}

// ═══════════════════════════════════════════════════════════════
// Quick Commands
// ═══════════════════════════════════════════════════════════════

function quickCmd(cmd) {
  const input = document.getElementById('command');
  if (input) {
    input.value = cmd;
    sendCommand();
  }
}

// ═══════════════════════════════════════════════════════════════
// Conversation
// ═══════════════════════════════════════════════════════════════

function addMessage(sender, text, isUser = false) {
  const conversation = document.getElementById('conversation');
  if (!conversation) return;
  
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { 
    hour12: false, 
    hour: '2-digit', 
    minute: '2-digit', 
    second: '2-digit' 
  });
  
  const messageBlock = document.createElement('div');
  messageBlock.className = 'message-block';
  messageBlock.innerHTML = `
    <div class="message-meta">
      <span class="sender ${isUser ? 'user' : 'kira'}">${sender}</span>
      <span class="timestamp">${timeStr}</span>
    </div>
    <div class="message">${text}</div>
  `;
  
  conversation.appendChild(messageBlock);
  conversation.scrollTop = conversation.scrollHeight;
}

function clearConversation() {
  const conversation = document.getElementById('conversation');
  if (conversation) {
    conversation.innerHTML = '';
    addMessage('KIRA', 'Conversation cleared, sir. How may I assist you?');
  }
}

// ═══════════════════════════════════════════════════════════════
// Activity Indicator
// ═══════════════════════════════════════════════════════════════

function setActivity(state) {
  const indicator = document.getElementById('activity-indicator');
  const activityText = document.getElementById('activity');
  
  if (!indicator || !activityText) return;
  
  indicator.className = 'activity-indicator';
  
  switch(state) {
    case 'thinking':
      indicator.classList.add('thinking');
      activityText.textContent = 'PROCESSING';
      if (typeof setSceneActivity === 'function') {
        setSceneActivity('thinking');
      }
      break;
    case 'speaking':
      indicator.classList.add('speaking');
      activityText.textContent = 'SPEAKING';
      if (typeof setSceneActivity === 'function') {
        setSceneActivity('speaking');
      }
      break;
    case 'active':
      indicator.classList.add('active');
      activityText.textContent = 'ACTIVE';
      if (typeof setSceneActivity === 'function') {
        setSceneActivity('active');
      }
      break;
    default:
      activityText.textContent = 'STANDBY';
      if (typeof setSceneActivity === 'function') {
        setSceneActivity('standby');
      }
  }
}

// ═══════════════════════════════════════════════════════════════
// Text-to-Speech
// ═══════════════════════════════════════════════════════════════

async function speakText(text) {
  if (isMuted || !text) return;
  
  // Stop current audio
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  
  setActivity('speaking');
  
  try {
    const response = await fetch(`${API_BASE}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    
    const data = await response.json();
    
    if (data.audio) {
      const audioBlob = new Blob(
        [Uint8Array.from(atob(data.audio), c => c.charCodeAt(0))],
        { type: 'audio/mp3' }
      );
      const audioUrl = URL.createObjectURL(audioBlob);
      
      currentAudio = new Audio(audioUrl);
      
      currentAudio.onended = () => {
        setActivity('active');
        URL.revokeObjectURL(audioUrl);
        currentAudio = null;
      };
      
      currentAudio.onerror = () => {
        console.error('[KIRA] Audio playback error');
        setActivity('active');
        URL.revokeObjectURL(audioUrl);
        currentAudio = null;
      };
      
      await currentAudio.play();
    } else {
      setActivity('active');
    }
  } catch (error) {
    console.error('[KIRA] TTS error:', error);
    setActivity('active');
  }
}

function toggleMute() {
  isMuted = !isMuted;
  const muteBtn = document.getElementById('mute');
  
  if (muteBtn) {
    if (isMuted) {
      muteBtn.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
          <line x1="23" y1="9" x2="17" y2="15"></line>
          <line x1="17" y1="9" x2="23" y2="15"></line>
        </svg>
      `;
      muteBtn.title = 'Unmute voice';
      
      if (currentAudio) {
        currentAudio.pause();
        currentAudio = null;
        setActivity('active');
      }
    } else {
      muteBtn.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
        </svg>
      `;
      muteBtn.title = 'Mute voice';
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// Voice Input
// ═══════════════════════════════════════════════════════════════

let recognition = null;
let isListening = false;

function toggleVoiceInput() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    addMessage('KIRA', 'I apologize, sir. Voice input is not supported in your browser.');
    return;
  }
  
  if (!recognition) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    
    recognition.onstart = () => {
      isListening = true;
      const micBtn = document.getElementById('mic');
      if (micBtn) {
        micBtn.style.background = 'var(--danger)';
        micBtn.style.borderColor = 'var(--danger)';
      }
      setActivity('active');
    };
    
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      const input = document.getElementById('command');
      if (input) {
        input.value = transcript;
        sendCommand();
      }
    };
    
    recognition.onerror = (event) => {
      console.error('[KIRA] Voice recognition error:', event.error);
      addMessage('KIRA', 'I apologize, sir. I encountered an error with voice recognition.');
    };
    
    recognition.onend = () => {
      isListening = false;
      const micBtn = document.getElementById('mic');
      if (micBtn) {
        micBtn.style.background = '';
        micBtn.style.borderColor = '';
      }
      setActivity('active');
    };
  }
  
  if (isListening) {
    recognition.stop();
  } else {
    recognition.start();
  }
}

// ═══════════════════════════════════════════════════════════════
// System Monitoring
// ═══════════════════════════════════════════════════════════════

function startSystemMonitoring() {
  updateSystemInfo();
  setInterval(updateSystemInfo, 3000);
}

async function updateSystemInfo() {
  try {
    const response = await fetch(`${API_BASE}/api/system`);
    const data = await response.json();
    
    if (data.cpu !== undefined) {
      const cpuEl = document.getElementById('cpu');
      const cpuBar = document.getElementById('cpu-bar');
      if (cpuEl) cpuEl.textContent = `${data.cpu}%`;
      if (cpuBar) cpuBar.style.width = `${data.cpu}%`;
    }
    
    if (data.memory !== undefined) {
      const memEl = document.getElementById('memory');
      const memBar = document.getElementById('memory-bar');
      if (memEl) memEl.textContent = `${data.memory}%`;
      if (memBar) memBar.style.width = `${data.memory}%`;
    }
    
    if (data.gpu !== undefined) {
      const gpuEl = document.getElementById('gpu');
      if (gpuEl) gpuEl.textContent = data.gpu || 'N/A';
    }
    
  } catch (error) {
    console.error('[KIRA] System monitoring error:', error);
  }
}

// ═══════════════════════════════════════════════════════════════
// Tasks
// ═══════════════════════════════════════════════════════════════

async function updateTasks() {
  try {
    const response = await fetch(`${API_BASE}/api/tasks`);
    const data = await response.json();
    
    const tasksList = document.getElementById('tasks-list');
    if (!tasksList) return;
    
    if (data.tasks && data.tasks.length > 0) {
      tasksList.innerHTML = data.tasks.map(task => `
        <div class="task-item">
          <div class="task-bullet"></div>
          <span>${task}</span>
        </div>
      `).join('');
    } else {
      tasksList.innerHTML = '<div class="task-empty">No pending tasks</div>';
    }
  } catch (error) {
    console.error('[KIRA] Tasks error:', error);
  }
}

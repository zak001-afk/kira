/* ═══════════════════════════════════════════════════════════════
   KIRA — Holographic Interface
   Main Application Logic
   ═══════════════════════════════════════════════════════════════ */

// ═══════════════════════════════════════════════════════════════
// Particle Background Animation
// ═══════════════════════════════════════════════════════════════

const canvas = document.getElementById('particles');
const ctx = canvas.getContext('2d');

let particles = [];
const particleCount = 80;

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}

class Particle {
  constructor() {
    this.reset();
  }

  reset() {
    this.x = Math.random() * canvas.width;
    this.y = Math.random() * canvas.height;
    this.size = Math.random() * 2 + 0.5;
    this.speedX = (Math.random() - 0.5) * 0.5;
    this.speedY = (Math.random() - 0.5) * 0.5;
    this.opacity = Math.random() * 0.5 + 0.2;
  }

  update() {
    this.x += this.speedX;
    this.y += this.speedY;

    if (this.x < 0 || this.x > canvas.width) this.speedX *= -1;
    if (this.y < 0 || this.y > canvas.height) this.speedY *= -1;
  }

  draw() {
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(0, 212, 255, ${this.opacity})`;
    ctx.fill();
  }
}

function initParticles() {
  particles = [];
  for (let i = 0; i < particleCount; i++) {
    particles.push(new Particle());
  }
}

function connectParticles() {
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x;
      const dy = particles[i].y - particles[j].y;
      const distance = Math.sqrt(dx * dx + dy * dy);

      if (distance < 150) {
        const opacity = (1 - distance / 150) * 0.2;
        ctx.beginPath();
        ctx.strokeStyle = `rgba(0, 212, 255, ${opacity})`;
        ctx.lineWidth = 0.5;
        ctx.moveTo(particles[i].x, particles[i].y);
        ctx.lineTo(particles[j].x, particles[j].y);
        ctx.stroke();
      }
    }
  }
}

function animateParticles() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  particles.forEach(particle => {
    particle.update();
    particle.draw();
  });
  
  connectParticles();
  requestAnimationFrame(animateParticles);
}

// ═══════════════════════════════════════════════════════════════
// Clock & Date Display
// ═══════════════════════════════════════════════════════════════

function updateClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
  const dateStr = now.toLocaleDateString('en-US', { 
    weekday: 'short', 
    month: 'short', 
    day: 'numeric' 
  });
  
  document.getElementById('time').textContent = timeStr;
  document.getElementById('date').textContent = dateStr;
}

// ═══════════════════════════════════════════════════════════════
// Boot Time Display
// ═══════════════════════════════════════════════════════════════

function setBootTime() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { 
    hour: '2-digit', 
    minute: '2-digit',
    hour12: false 
  });
  document.getElementById('boot-time').textContent = timeStr;
}

// ═══════════════════════════════════════════════════════════════
// System Telemetry
// ═══════════════════════════════════════════════════════════════

async function updateSystemTelemetry() {
  try {
    const response = await fetch('http://localhost:8765/api/system');
    const data = await response.json();
    
    if (data.cpu !== undefined) {
      document.getElementById('cpu').textContent = `${data.cpu}%`;
      document.getElementById('cpu-bar').style.width = `${data.cpu}%`;
    }
    
    if (data.memory !== undefined) {
      document.getElementById('memory').textContent = `${data.memory}%`;
      document.getElementById('memory-bar').style.width = `${data.memory}%`;
    }
    
    if (data.gpu) {
      document.getElementById('gpu').textContent = data.gpu;
    }
  } catch (error) {
    console.error('Failed to fetch system telemetry:', error);
  }
}

// ═══════════════════════════════════════════════════════════════
// Task Management
// ═══════════════════════════════════════════════════════════════

async function updateTasks() {
  try {
    const response = await fetch('http://localhost:8765/api/tasks');
    const data = await response.json();
    
    const tasksList = document.getElementById('tasks-list');
    
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
    console.error('Failed to fetch tasks:', error);
  }
}

// ═══════════════════════════════════════════════════════════════
// Activity Indicator
// ═══════════════════════════════════════════════════════════════

function setActivity(state) {
  const dot = document.getElementById('activity-dot');
  const label = document.getElementById('activity');
  
  dot.className = 'indicator-dot';
  
  switch(state) {
    case 'thinking':
      dot.classList.add('thinking');
      label.textContent = 'Thinking';
      break;
    case 'speaking':
      dot.classList.add('speaking');
      label.textContent = 'Speaking';
      break;
    case 'active':
      dot.classList.add('active');
      label.textContent = 'Active';
      break;
    default:
      label.textContent = 'Standby';
  }
}

// ═══════════════════════════════════════════════════════════════
// Conversation Management
// ═══════════════════════════════════════════════════════════════

function addMessage(sender, text, isUser = false) {
  const conversation = document.getElementById('conversation');
  const now = new Date();
  const timeStr = now.toLocaleTimeString('en-US', { 
    hour: '2-digit', 
    minute: '2-digit',
    hour12: false 
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
  conversation.innerHTML = '';
  addMessage('KIRA', 'Conversation cleared, sir. How may I assist you?');
}

// ═══════════════════════════════════════════════════════════════
// Command Processing
// ═══════════════════════════════════════════════════════════════

let speechEnabled = true;
let recognition = null;
let currentAudio = null;

async function sendCommand() {
  const input = document.getElementById('command');
  const text = input.value.trim();
  
  if (!text) return;
  
  addMessage('You', text, true);
  input.value = '';
  
  setActivity('thinking');
  
  try {
    const response = await fetch('http://localhost:8765/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    
    const data = await response.json();
    
    if (data.response) {
      addMessage('KIRA', data.response);
      
      if (speechEnabled && data.response) {
        speakText(data.response);
      }
    }
    
    setActivity('standby');
    
    // Refresh tasks if command might have affected them
    if (text.toLowerCase().includes('task') || text.toLowerCase().includes('remind')) {
      setTimeout(updateTasks, 500);
    }
  } catch (error) {
    console.error('Command failed:', error);
    addMessage('KIRA', 'I apologize, sir. I encountered an error processing your request.');
    setActivity('standby');
  }
}

// ═══════════════════════════════════════════════════════════════
// Voice Input (Speech Recognition)
// ═══════════════════════════════════════════════════════════════

function initSpeechRecognition() {
  if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';
    
    recognition.onstart = () => {
      document.getElementById('mic').classList.add('listening');
      setActivity('active');
    };
    
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      document.getElementById('command').value = transcript;
      sendCommand();
    };
    
    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      document.getElementById('mic').classList.remove('listening');
      setActivity('standby');
    };
    
    recognition.onend = () => {
      document.getElementById('mic').classList.remove('listening');
      setActivity('standby');
    };
  }
}

function toggleMicrophone() {
  if (!recognition) {
    addMessage('KIRA', 'I apologize, sir. Voice input is not supported in your browser.');
    return;
  }
  
  if (document.getElementById('mic').classList.contains('listening')) {
    recognition.stop();
  } else {
    recognition.start();
  }
}

// ═══════════════════════════════════════════════════════════════
// Voice Output (Text-to-Speech)
// ═══════════════════════════════════════════════════════════════

async function speakText(text) {
  if (!speechEnabled) return;
  
  // Stop any current speech
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  
  setActivity('speaking');
  
  try {
    const response = await fetch('http://localhost:8765/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    
    const data = await response.json();
    
    if (data.audio) {
      const audioBlob = new Blob([Uint8Array.from(atob(data.audio), c => c.charCodeAt(0))], { type: 'audio/mp3' });
      const audioUrl = URL.createObjectURL(audioBlob);
      
      currentAudio = new Audio(audioUrl);
      
      currentAudio.onended = () => {
        setActivity('standby');
        URL.revokeObjectURL(audioUrl);
        currentAudio = null;
      };
      
      currentAudio.onerror = () => {
        console.error('Audio playback error');
        setActivity('standby');
        URL.revokeObjectURL(audioUrl);
        currentAudio = null;
      };
      
      await currentAudio.play();
    } else {
      setActivity('standby');
    }
  } catch (error) {
    console.error('TTS failed:', error);
    setActivity('standby');
  }
}

function toggleMute() {
  speechEnabled = !speechEnabled;
  const muteBtn = document.getElementById('mute');
  
  if (speechEnabled) {
    muteBtn.innerHTML = `
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path>
      </svg>
    `;
    muteBtn.title = 'Mute voice';
  } else {
    muteBtn.innerHTML = `
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
        <line x1="23" y1="9" x2="17" y2="15"></line>
        <line x1="17" y1="9" x2="23" y2="15"></line>
      </svg>
    `;
    muteBtn.title = 'Unmute voice';
    
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
      setActivity('standby');
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// Quick Commands
// ═══════════════════════════════════════════════════════════════

function quickCmd(command) {
  document.getElementById('command').value = command;
  sendCommand();
}

// ═══════════════════════════════════════════════════════════════
// Event Listeners
// ═══════════════════════════════════════════════════════════════

document.getElementById('send').addEventListener('click', sendCommand);

document.getElementById('command').addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    sendCommand();
  }
});

document.getElementById('mic').addEventListener('click', toggleMicrophone);
document.getElementById('mute').addEventListener('click', toggleMute);
document.getElementById('clear-chat').addEventListener('click', clearConversation);

window.addEventListener('resize', () => {
  resizeCanvas();
  initParticles();
});

// ═══════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════

function init() {
  // Initialize particle background
  resizeCanvas();
  initParticles();
  animateParticles();
  
  // Initialize clock
  updateClock();
  setInterval(updateClock, 1000);
  
  // Set boot time
  setBootTime();
  
  // Initialize speech recognition
  initSpeechRecognition();
  
  // Update system telemetry every 3 seconds
  updateSystemTelemetry();
  setInterval(updateSystemTelemetry, 3000);
  
  // Update tasks every 10 seconds
  updateTasks();
  setInterval(updateTasks, 10000);
  
  // Focus command input
  document.getElementById('command').focus();
}

// Start the application
init();

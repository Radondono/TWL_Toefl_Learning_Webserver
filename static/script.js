// ─── Shared TTS Voice ───
let ttsVoiceName = null;
let ttsVoice = null;

async function loadTTSVoice() {
    try {
        const res = await fetch('/api/settings/tts_voice');
        const data = await res.json();
        ttsVoiceName = data.voice || '';
        if (ttsVoiceName) {
            const voices = window.speechSynthesis.getVoices();
            ttsVoice = voices.find(v => v.name === ttsVoiceName) || null;
        }
    } catch (e) {
        console.warn('Could not load voice setting:', e);
    }
}

function initVoice() {
    loadTTSVoice().then(() => {
        if (!ttsVoice) {
            const voices = window.speechSynthesis.getVoices();
            const femaleNames = ['Samantha', 'Victoria', 'Karen', 'Google UK English Female', 'Microsoft Zira'];
            for (const name of femaleNames) {
                const v = voices.find(v => v.name.includes(name));
                if (v) { ttsVoice = v; break; }
            }
            if (!ttsVoice && voices.length > 0) ttsVoice = voices[0];
        }
    });
}

function playSound(word) {
    const utterance = new SpeechSynthesisUtterance(word);
    utterance.lang = 'en-US';
    utterance.rate = 0.9;
    if (ttsVoice) {
        utterance.voice = ttsVoice;
    }
    window.speechSynthesis.speak(utterance);
}

// ─── Attach Speaker Buttons (class .speaker-btn) ───
function attachSpeakerButtons() {
    document.querySelectorAll('.speaker-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const word = this.dataset.word;
            if (word) playSound(word);
        });
    });
}

// ─── Toggle Details (class .toggle-details) ───
function attachToggleDetails() {
    document.querySelectorAll('.toggle-details').forEach(el => {
        el.addEventListener('click', function(e) {
            e.stopPropagation();
            const targetId = this.dataset.target;
            const row = document.getElementById(targetId);
            if (row) {
                row.classList.toggle('show');
                this.textContent = row.classList.contains('show') ? '[hide]' : '[details]';
            }
        });
    });
}

// ─── Table Sorting ───
function attachTableSorting(tableId = 'wordTable', bodyId = 'tableBody') {
    const table = document.getElementById(tableId);
    if (!table) return;
    const headers = table.querySelectorAll('.sortable');
    headers.forEach(th => {
        th.addEventListener('click', function() {
            const tbody = document.getElementById(bodyId);
            if (!tbody) return;
            const mainRows = Array.from(tbody.querySelectorAll('tr:not(.row-details)'));
            const currentDir = this.classList.contains('asc') ? 'asc' : (this.classList.contains('desc') ? 'desc' : null);
            document.querySelectorAll('.sortable').forEach(h => h.classList.remove('asc', 'desc'));
            let newDir = 'asc';
            if (currentDir === 'asc') {
                this.classList.add('desc');
                newDir = 'desc';
            } else {
                this.classList.add('asc');
            }
            const sortKey = this.dataset.sort;
            const statusOrder = { 'mastered': 0, 'learning': 1, 'not_started': 2 };
            mainRows.sort((a, b) => {
                let valA, valB;
                const cellsA = a.querySelectorAll('td');
                const cellsB = b.querySelectorAll('td');
                if (sortKey === 'word') {
                    valA = cellsA[0].textContent.trim().toLowerCase();
                    valB = cellsB[0].textContent.trim().toLowerCase();
                } else if (sortKey === 'pos') {
                    valA = cellsA[2].textContent.trim().toLowerCase();
                    valB = cellsB[2].textContent.trim().toLowerCase();
                } else if (sortKey === 'diff') {
                    valA = parseInt(cellsA[3].textContent) || 0;
                    valB = parseInt(cellsB[3].textContent) || 0;
                } else if (sortKey === 'status') {
                    const getStatus = (el) => {
                        const txt = el.textContent;
                        if (txt.includes('Mastered')) return 'mastered';
                        if (txt.includes('Learning')) return 'learning';
                        return 'not_started';
                    };
                    valA = statusOrder[getStatus(cellsA[4])];
                    valB = statusOrder[getStatus(cellsB[4])];
                } else if (sortKey === 'difficult') {
                    valA = cellsA[7].querySelector('button').textContent.includes('⭐') ? 1 : 0;
                    valB = cellsB[7].querySelector('button').textContent.includes('⭐') ? 1 : 0;
                } else {
                    const idx = sortKey === 'attempts' ? 5 : 6;
                    valA = parseInt(cellsA[idx].textContent) || 0;
                    valB = parseInt(cellsB[idx].textContent) || 0;
                }
                if (valA < valB) return newDir === 'asc' ? -1 : 1;
                if (valA > valB) return newDir === 'asc' ? 1 : -1;
                return 0;
            });
            const detailRows = Array.from(tbody.querySelectorAll('.row-details'));
            tbody.innerHTML = '';
            mainRows.forEach(row => {
                const rowId = row.querySelector('.toggle-details')?.dataset.target;
                tbody.appendChild(row);
                const detail = detailRows.find(d => d.id === rowId);
                if (detail) tbody.appendChild(detail);
            });
        });
    });
}

// ─── Toggle Difficult (AJAX) ───
function attachToggleDifficult() {
    document.querySelectorAll('.toggle-diff').forEach(btn => {
        btn.addEventListener('click', async function() {
            const word = this.dataset.word;
            try {
                const res = await fetch('/api/toggle_difficult', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ word: word })
                });
                const data = await res.json();
                if (data.message) {
                    window.location.reload();
                } else {
                    alert('Error: ' + (data.error || 'Unknown'));
                }
            } catch (e) {
                alert('Network error.');
            }
        });
    });
}

// ─── Initialise voice ───
if (window.speechSynthesis.onvoiceschanged !== undefined) {
    window.speechSynthesis.onvoiceschanged = initVoice;
}
setTimeout(initVoice, 100);

// ─── Auto‑attach on DOM ready ───
document.addEventListener('DOMContentLoaded', function() {
    attachSpeakerButtons();
    attachToggleDetails();
    attachTableSorting('wordTable', 'tableBody');
    attachToggleDifficult();
});
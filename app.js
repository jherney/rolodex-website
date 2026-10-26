/* Rolodex Contacts - Frontend Logic */
/* This file implements the interactive UI for the Rolodex contacts app */

let contacts = [];
let filteredContacts = [];
let selectedContactId = null;
let currentFilterTag = 'all';
let currentSearchTerm = '';
let wheelIndex = 0; // index of contact displayed at "front" of wheel
const WHEEL_VISIBLE_COUNT = 5; // front card plus the cards peeking up behind it
let flipDirection = 0; // 1 = flipped to the next card, -1 = previous; animates the next render

// DOM Elements
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const clearBtn = document.getElementById('clearBtn');
const filterBySelect = document.getElementById('filterBy');
const addContactBtn = document.getElementById('addContactBtn');
const importBtn = document.getElementById('importBtn');
const exportBtn = document.getElementById('exportBtn');
const duplicatesBtn = document.getElementById('duplicatesBtn');
const fileInput = document.getElementById('fileInput');
const rolodexWheel = document.getElementById('rolodexWheel');
const rotateLeftBtn = document.getElementById('rotateLeftBtn');
const rotateRightBtn = document.getElementById('rotateRightBtn');
const cardCountSpan = document.getElementById('cardCount');
const totalCountSpan = document.getElementById('totalCount');

// Modals
const contactModal = document.getElementById('contactModal');
const modalTitle = document.getElementById('modalTitle');
const contactForm = document.getElementById('contactForm');
const contactIdInput = document.getElementById('contactId');
const nameInput = document.getElementById('name');
const birthdayInput = document.getElementById('birthday');
const phoneInput = document.getElementById('phone');
const emailInput = document.getElementById('email');
const addressInput = document.getElementById('address');
const socialInput = document.getElementById('social');
const avatarUrlInput = document.getElementById('avatarUrl');
const avatarFileInput = document.getElementById('avatarFile');
const avatarPreview = document.getElementById('avatarPreview');
const avatarInitials = document.getElementById('avatarInitials');
const tagsEditor = document.getElementById('tagsEditor');
const tagsList = document.getElementById('tagsList');
const tagsInput = document.getElementById('tagsInput');
const addTagBtn = document.getElementById('addTagBtn');
const suggestedTags = document.getElementById('suggestedTags');
const notesInput = document.getElementById('notes');
const notesPreview = document.getElementById('notesPreview');
const linkedContactsDiv = document.getElementById("linkedContacts");
const deleteContactBtn = document.getElementById('deleteContactBtn');
const saveBtn = contactForm.querySelector('.save-btn');
const closeModalBtn = contactModal.querySelector('.close');
const shortcutsModal = document.getElementById('shortcutsModal');
const closeShortcuts = document.getElementById('closeShortcuts');
const bulkTagModal = document.getElementById('bulkTagModal');
const closeBulkTag = document.getElementById('closeBulkTag');
const bulkTagInfo = document.getElementById('bulkTagInfo');
const bulkTagInput = document.getElementById('bulkTagInput');
const bulkTagApplyBtn = document.getElementById('bulkTagApplyBtn');
const mergeModal = document.getElementById('mergeModal');
const closeMerge = document.getElementById('closeMerge');
const mergeInfo = document.getElementById('mergeInfo');
const mergeBody = document.getElementById('mergeBody');
const mergeCancelBtn = document.getElementById('mergeCancelBtn');
const mergeApplyBtn = document.getElementById('mergeApplyBtn');
const importModal = document.getElementById('importModal');
const closeImport = document.getElementById('closeImport');
const importSummary = document.getElementById('importSummary');
const importRows = document.getElementById('importRows');
const importCancelBtn = document.getElementById('importCancelBtn');
const importConfirmBtn = document.getElementById('importConfirmBtn');
const duplicatesModal = document.getElementById('duplicatesModal');
const closeDuplicates = document.getElementById('closeDuplicates');
const duplicatesInfo = document.getElementById('duplicatesInfo');
const duplicatesList = document.getElementById('duplicatesList');
let pendingImportFile = null; // file previewed in the import dialog, written only on confirm
const birthdayBar = document.getElementById('birthdayBar');
const birthdayBarContent = document.getElementById('birthdayBarContent');
const birthdayCloseBtn = document.getElementById('birthdayCloseBtn');
const themeToggle = document.getElementById('themeToggle');
const shortcutsBtn = document.getElementById('shortcutsBtn');
const closePanelBtn = document.querySelector('.close-panel');
const editPanelBtn = document.querySelector('.edit-btn');
const shareContactBtn = document.getElementById('shareContactBtn');
const prevContactBtn = document.querySelector('.prev-btn');
const nextContactBtn = document.querySelector('.next-btn');

// State for bulk operations
let selectedContacts = new Set();

// State for merge
let mergeContacts = []; // will hold two contact objects

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  loadTheme();
  await loadContacts();
  setupEventListeners();
  renderWheel();
  updateCounters();
});

// Load theme from localStorage or system preference
function loadTheme() {
  const savedTheme = localStorage.getItem('theme');
  if (savedTheme) {
    document.documentElement.setAttribute('color-scheme', savedTheme);
  } else {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('color-scheme', prefersDark ? 'dark' : 'light');
  }
}

// Theme toggle
themeToggle.addEventListener('click', () => {
  const current = document.documentElement.getAttribute('color-scheme');
  const newTheme = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('color-scheme', newTheme);
  localStorage.setItem('theme', newTheme);
});

// Shortcuts modal
shortcutsBtn.addEventListener('click', () => shortcutsModal.showModal());
closeShortcuts.addEventListener('click', () => shortcutsModal.close());

// Close modals when clicking outside (dialog handles backdrop, but we handle X)
        closeModalBtn.addEventListener('click', () => contactModal.close());
        closeBulkTag.addEventListener('click', () => bulkTagModal.close());
        closeMerge.addEventListener('click', () => mergeModal.close());
        birthdayCloseBtn.addEventListener('click', () => birthdayBar.style.display = 'none');

// Event Listeners
function setupEventListeners() {
  // Search
  searchBtn.addEventListener('click', handleSearch);
  clearBtn.addEventListener('click', handleClearSearch);
  searchInput.addEventListener('keypress', e => {
    if (e.key === 'Enter') handleSearch();
  });

  // Filter
  filterBySelect.addEventListener('change', handleFilterChange);

  // Contacts
  addContactBtn.addEventListener('click', () => openContactModal(null));
  importBtn.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', handleFileImport);
  exportBtn.addEventListener('click', handleExport);
  duplicatesBtn.addEventListener('click', handleDuplicates);

  // Wheel rotation
  rotateLeftBtn.addEventListener('click', () => rotateWheel(-1));
  rotateRightBtn.addEventListener('click', () => rotateWheel(1));

  // Form
  contactForm.addEventListener('submit', handleContactFormSubmit);
  addTagBtn.addEventListener('click', () => addTagFromInput());
  tagsInput.addEventListener('keypress', e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addTagFromInput();
    }
  });
  avatarUrlInput.addEventListener('change', updateAvatarPreview);
  avatarFileInput.addEventListener('change', handleAvatarFileSelect);
  nameInput.addEventListener('input', updateAvatarInitials);
  notesInput.addEventListener('input', updateNotesPreview);

  // Modal buttons
  deleteContactBtn.addEventListener('click', handleDeleteContact);
  saveBtn.addEventListener('click', e => {
    e.preventDefault();
    contactForm.dispatchEvent(new Event('submit'));
  });

  // Bulk tag
  bulkTagApplyBtn.addEventListener('click', handleBulkTagApply);

  // Merge
  mergeCancelBtn.addEventListener('click', () => mergeModal.close());
  mergeApplyBtn.addEventListener('click', handleMergeApply);
  mergeModal.addEventListener('close', resetMergeState);

  // Import preview and duplicate review
  importConfirmBtn.addEventListener('click', handleImportConfirm);
  importCancelBtn.addEventListener('click', () => importModal.close());
  closeImport.addEventListener('click', () => importModal.close());
  importModal.addEventListener('close', resetImportState);
  closeDuplicates.addEventListener('click', () => duplicatesModal.close());

  // Merge selection via shift-click on wheel cards
  let mergeSelectMode = false;
  document.addEventListener('keydown', e => {
    if (e.key === 'Shift') mergeSelectMode = true;
  });
  document.addEventListener('keyup', e => {
    if (e.key === 'Shift') mergeSelectMode = false;
  });
  rolodexWheel.addEventListener('click', e => {
    const card = e.target.closest('.rolodex-card');
    if (!card) return;
    if (mergeSelectMode) {
      const contactId = card.dataset.contactId;
      const contact = contacts.find(c => c.id === contactId);
      if (contact && !mergeContacts.includes(contact)) {
        mergeContacts.push(contact);
        card.classList.add('selected-for-merge');
        if (mergeContacts.length === 2) {
          openMergeDialog(mergeContacts[0], mergeContacts[1]);
        }
      }
    }
  });

  // Panel buttons
  closePanelBtn?.addEventListener('click', hideContactPanel);
  editPanelBtn?.addEventListener('click', editSelectedContact);
  shareContactBtn?.addEventListener('click', shareSelectedContact);
  prevContactBtn?.addEventListener('click', previousCard);
  nextContactBtn?.addEventListener('click', nextCard);
}

// ----- Data Loading & Filtering -----
function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
}

async function loadContacts() {
  try {
    const response = await fetch('/api/v1/contacts');
    const data = await response.json();
    // Ensure all contacts have valid IDs
    contacts = data.map(c => {
      if (!c.id || c.id === '') {
        return { ...c, id: generateId() };
      }
      return c;
    }).sort(compareByFilingName);
    applyFiltersAndSearch();
  } catch (err) {
    console.error('Failed to load contacts:', err);
    showToast('Failed to load contacts');
  }
}

function applyFiltersAndSearch() {
  let filtered = contacts;
  // Search
  if (currentSearchTerm.trim() !== '') {
    const terms = currentSearchTerm.toLowerCase().trim().split(/\s+/);
    filtered = filtered.filter(c => {
      const searchable = [
        c.name || '',
        c.phone || '',
        c.email || '',
        c.address || '',
        c.notes || '',
        c.company || '',
        c.title || '',
        (c.tags || []).join(' ')
      ].join(' ').toLowerCase();
      return terms.every(term => searchable.includes(term));
    });
  }
  // Tag filter
  // Tag filter
  if (currentFilterTag !== "all") {
    filtered = filtered.filter(c => 
      (c.tags || []).some(tag => tag.toLowerCase() === currentFilterTag.toLowerCase())
    );
  }
  filteredContacts = filtered;
  updateWheelIndexIfNeeded();
  renderWheel();
  updateCounters();
}

function updateWheelIndexIfNeeded() {
  if (filteredContacts.length === 0) {
    wheelIndex = 0;
    return;
  }
  // Ensure wheelIndex is within bounds
  if (wheelIndex >= filteredContacts.length) {
    wheelIndex = filteredContacts.length - 1;
  }
  if (wheelIndex < 0) wheelIndex = 0;
}

// ----- Wheel Rendering -----
function renderWheel() {
  // Clear wheel
  rolodexWheel.innerHTML = '';

  if (filteredContacts.length === 0) {
    const emptyMsg = document.createElement('div');
    emptyMsg.className = 'empty-state';
    emptyMsg.textContent = contacts.length
      ? 'No cards match. Clear the search or choose another tag.'
      : 'No cards yet. Add a contact to start filing.';
    rolodexWheel.appendChild(emptyMsg);
    flipDirection = 0;
    return;
  }

  // Back cards first so the front card (depth 0) is painted on top
  const visibleCount = Math.min(WHEEL_VISIBLE_COUNT, filteredContacts.length);
  for (let depth = visibleCount - 1; depth >= 0; depth--) {
    const idx = (wheelIndex + depth) % filteredContacts.length;
    rolodexWheel.appendChild(createCard(filteredContacts[idx], idx, depth));
  }
  flipDirection = 0;
}

function createCard(contact, idx, depth) {
  const card = document.createElement('div');
  card.className = 'rolodex-card';
  if (depth === 0) {
    card.classList.add('center');
    if (flipDirection) card.classList.add(flipDirection > 0 ? 'flip-next' : 'flip-prev');
  }
  card.style.setProperty('--depth', depth);
  const filedName = filingName(contact.name);
  card.style.setProperty('--tab-x', cardTabOffset(filedName));
  if (depth > 0) card.title = contact.name || '';
  card.dataset.index = idx;
  card.dataset.contactId = contact.id;
  card.innerHTML = `
      <div class="card-tab">${cardLetter(filedName)}</div>
      <div class="card-inner">
        <div class="card-avatar">
          <span class="avatar-initials">${escapeHtml(getInitials(contact.name))}</span>
        </div>
        <div class="card-info">
          <h3 class="card-name">${escapeHtml(filedName)}</h3>
          <div class="card-tags">
            ${(contact.tags || []).slice(0, 1).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('')}${contact.tags && contact.tags.length > 1 ? `<span class="tag tag-more">+${contact.tags.length - 1}</span>` : ''}
          </div>
          <div class="card-contact">
            ${contact.phone ? `<span class="contact-item">📞 ${escapeHtml(contact.phone)}</span>` : ''}
            ${contact.email ? `<span class="contact-item">✉️ ${escapeHtml(contact.email)}</span>` : ''}
          </div>
        </div>
      </div>
    `;
  card.addEventListener('click', e => {
    // Shift-click is merge selection (handled on the wheel); re-rendering here would detach the card
    if (e.shiftKey) return;
    selectContact(contact.id);
    // Cards behind the front one are reached by flipping forward
    flipDirection = depth > 0 ? 1 : 0;
    wheelIndex = idx;
    renderWheel();
  });
  return card;
}

// "Alice Archer" -> "Archer, Alice": rolodex cards are filed by surname
function filingName(name) {
  const trimmed = (name || '').trim();
  if (trimmed.includes(',')) return trimmed; // already "Surname, Given"
  const parts = trimmed.split(/\s+/);
  if (parts.length < 2) return parts[0] || '';
  const surname = parts.pop();
  return `${surname}, ${parts.join(' ')}`;
}

// A–Z by surname, then given name ("Archer, Alice" before "Archer, Ben"); ignores case and accents
const filingCollator = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true });
function compareByFilingName(a, b) {
  return filingCollator.compare(filingName(a.name), filingName(b.name));
}

// Index-card tab letter; tabs are staggered across the top by letter so they peek out like a real rolodex
function cardLetter(name) {
  // "É" files under E
  const letter = (name || '').trim().charAt(0).normalize('NFD').charAt(0).toUpperCase();
  return /[A-Z]/.test(letter) ? letter : '#';
}

function cardTabOffset(name) {
  const letter = cardLetter(name);
  const slot = letter === '#' ? 0 : letter.charCodeAt(0) - 65;
  return `${8 + slot * 2.6}%`;
}

function selectContact(contactId) {
  selectedContactId = contactId;
  const contact = contacts.find(c => c.id === contactId);
  if (contact) {
    showContactPanel(contact);
  } else {
    hideContactPanel();
  }
}

function showContactPanel(contact) {
  const panel = document.getElementById('selectedCardPanel');
  panel.setAttribute('open', '');
  // Populate panel
  document.getElementById('panelName').textContent = contact.name || '';
  const panelAvatarInitials = document.getElementById('panelAvatarInitials');
  panelAvatarInitials.textContent = getInitials(contact.name);
  const panelTags = document.getElementById('panelTags');
  panelTags.innerHTML = (contact.tags || []).map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('');
  const panelBody = document.getElementById('panelBody');
  // Build panel body content
  // Only list the fields this contact actually has
  const social = Object.entries(contact.social || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
  const fields = [['Phone', contact.phone], ['Email', contact.email], ['Address', contact.address],
                  ['Birthday', contact.birthday], ['Social', social]];
  let html = fields.filter(([, value]) => value)
    .map(([label, value]) => `<p><strong>${label}:</strong> ${escapeHtml(value)}</p>`).join('');
  if (contact.notes) {
    html += `<p><strong>Notes:</strong></p>
        <div class="notes-content">${renderNotes(contact.notes)}</div>`;
  }
  // Linked contacts
  const linked = contact.linked_contacts || [];
  if (linked.length > 0) {
    html += `<p><strong>Linked contacts:</strong> ${linked.map(id => {
      const lc = contacts.find(c => c.id === id);
      return escapeHtml(lc ? lc.name : id);
    }).join(', ')}</p>`;
  }
  panelBody.innerHTML = html;
}

function hideContactPanel() {
  document.getElementById('selectedCardPanel').removeAttribute('open');
}


// ----- Panel Navigation & Actions -----
function editSelectedContact() {
  if (!selectedContactId) return;
  hideContactPanel();
  openContactModal(contacts.find(c => c.id === selectedContactId));
}

function shareSelectedContact() {
  if (!selectedContactId) return;
  const contact = contacts.find(c => c.id === selectedContactId);
  if (!contact) return;
  
  // Create vCard
  const vcard = [
    'BEGIN:VCARD',
    'VERSION:3.0',
    `FN:${contact.name || ''}`,
    contact.phone ? `TEL:${contact.phone}` : '',
    contact.email ? `EMAIL:${contact.email}` : '',
    contact.address ? `ADR:${contact.address}` : '',
    contact.birthday ? `BDAY:${contact.birthday}` : '',
    contact.notes ? `NOTE:${contact.notes}` : '',
    'END:VCARD'
  ].filter(Boolean).join('\n');
  
  const blob = new Blob([vcard], { type: 'text/vcard' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${contact.name || 'contact'}.vcf`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('vCard downloaded');
}

function previousCard() {
  if (!selectedContactId) return;
  const idx = filteredContacts.findIndex(c => c.id === selectedContactId);
  if (idx <= 0) return;
  const prevContact = filteredContacts[idx - 1];
  selectContact(prevContact.id);
  flipDirection = -1;
  wheelIndex = filteredContacts.indexOf(prevContact);
  renderWheel();
}

function nextCard() {
  if (!selectedContactId) return;
  const idx = filteredContacts.findIndex(c => c.id === selectedContactId);
  if (idx >= filteredContacts.length - 1) return;
  const nextContact = filteredContacts[idx + 1];
  selectContact(nextContact.id);
  flipDirection = 1;
  wheelIndex = filteredContacts.indexOf(nextContact);
  renderWheel();
}


// Rotate wheel
function rotateWheel(direction) {
  if (filteredContacts.length === 0) return;
  wheelIndex = (wheelIndex + direction + filteredContacts.length) % filteredContacts.length;
  flipDirection = direction;
  renderWheel();
}

// ----- Contact Modal -----
function openContactModal(contact) {
  // Reset form
  contactForm.reset();
  contactIdInput.value = '';
  modalTitle.textContent = contact ? 'Edit contact' : 'Add contact';
  deleteContactBtn.style.display = contact ? 'block' : 'none';
  selectedContactId = contact ? contact.id : null;
  if (contact) loadContactExtras(contact.id);
  else contactExtras.hidden = true;

  if (contact) {
    // Populate form
    contactIdInput.value = contact.id;
    nameInput.value = contact.name || '';
    birthdayInput.value = contact.birthday || '';
    phoneInput.value = contact.phone || '';
    emailInput.value = contact.email || '';
    addressInput.value = contact.address || '';
    socialInput.value = typeof contact.social === 'object' ? 
      Object.entries(contact.social).map(([k,v])=> `${k}: ${v}`).join(', ') : 
      contact.social || '';
    // Tags
    tagsList.innerHTML = '';
    (contact.tags || []).forEach(tag => addTagElement(tag));
    // Avatar
    avatarUrlInput.value = contact.avatar || '';
    updateAvatarPreview();
    avatarInitials.textContent = getInitials(contact.name);
    // Notes
    notesInput.value = contact.notes || '';
    updateNotesPreview();
    // Linked contacts (simplified - just show)
    renderLinkedContacts(contact.linked_contacts || []);
  } else {
    // Clear avatar preview
    avatarPreview.innerHTML = '<span class="avatar-initials">?</span>';
    avatarInitials.textContent = '?';
    tagsList.innerHTML = '';
    notesInput.value = '';
    notesPreview.innerHTML = '';
    linkedContactsDiv.innerHTML = '';
  }

  contactModal.showModal();
  nameInput.focus();
}

function addTagFromInput() {
  const tag = tagsInput.value.trim();
  if (tag && !tagsList.querySelector(`[data-tag="${tag}"]`)) {
    addTagElement(tag);
    tagsInput.value = '';
  }
}

function addTagElement(tag) {
  const span = document.createElement('span');
  span.className = 'tag';
  span.dataset.tag = tag;
  span.textContent = tag;
  const removeBtn = document.createElement('button');
  removeBtn.type = 'button'; // default "submit" would save the form
  removeBtn.className = 'tag-remove';
  removeBtn.innerHTML = '&times;';
  removeBtn.onclick = () => span.remove();
  span.appendChild(removeBtn);
  tagsList.appendChild(span);
}

function updateAvatarPreview() {
  const url = avatarUrlInput.value.trim();
  if (url) {
    const img = document.createElement('img');
    img.src = url;
    img.onerror = () => { img.onerror = null; img.alt = 'Failed to load'; img.src = ''; };
    avatarPreview.replaceChildren(img);
  } else {
    avatarPreview.innerHTML = `<span class="avatar-initials">${escapeHtml(getInitials(nameInput.value))}</span>`;
  }
}

function handleAvatarFileSelect(e) {
  const file = e.target.files[0];
  if (file) {
    const reader = new FileReader();
    reader.onload = function(e) {
      avatarPreview.innerHTML = `<img src="${e.target.result}">`;
      avatarUrlInput.value = ''; // clear URL input
    };
    reader.readAsDataURL(file);
  }
}

function updateAvatarInitials() {
  avatarInitials.textContent = getInitials(nameInput.value);
  // Also update preview if no URL
  if (!avatarUrlInput.value.trim()) {
    avatarPreview.innerHTML = `<span class="avatar-initials">${escapeHtml(avatarInitials.textContent)}</span>`;
  }
}

function updateNotesPreview() {
  notesPreview.innerHTML = renderNotes(notesInput.value);
}

// Notes are Markdown. Output is sanitized because notes can arrive through imports.
function renderNotes(text) {
  const value = text || '';
  if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') return escapeHtml(value);
  return DOMPurify.sanitize(marked.parse(value));
}

function getInitials(name) {
  if (!name) return '?';
  return name
    .split(' ')
    .map(part => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

function renderLinkedContacts(linkedIds) {
  linkedContactsDiv.innerHTML = '';
  if (!linkedIds || linkedIds.length === 0) {
    linkedContactsDiv.innerHTML = '<em>None</em>';
    return;
  }
  linkedIds.forEach(id => {
    const contact = contacts.find(c => c.id === id);
    if (contact) {
      const span = document.createElement('span');
      span.className = 'linked-contact';
      span.textContent = contact.name;
      span.title = `ID: ${id}`;
      linkedContactsDiv.appendChild(span);
    }
  });
}

// ----- Form Submission -----
async function handleContactFormSubmit(e) {
  e.preventDefault();
  const isEdit = !!contactIdInput.value;
  const method = isEdit ? 'PUT' : 'POST';
  const url = isEdit ? `/api/v1/contacts/${contactIdInput.value}` : '/api/v1/contacts';
  
  // Build contact object
  const contact = {
    id: contactIdInput.value || '',
    name: nameInput.value.trim(),
    phone: phoneInput.value.trim(),
    email: emailInput.value.trim(),
    address: addressInput.value.trim(),
    birthday: birthdayInput.value,
    social: parseSocial(socialInput.value),
    tags: Array.from(tagsList.querySelectorAll('.tag')).map(t => t.dataset.tag),
    notes: notesInput.value.trim(),
    avatar: avatarUrlInput.value.trim() || ''
    // linked_contacts and starred have no form fields; omitting them keeps their saved values on edit
  };
  
  // Validate
  if (!contact.name) {
    showToast('Name is required');
    return;
  }

  try {
    const response = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(contact)
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || 'Failed to save contact');
    }
    
    const result = await response.json();
    showToast(isEdit ? 'Contact updated' : 'Contact added');
    contactModal.close();
    await loadContacts();
    // Contacts are re-sorted by surname, so bring the saved card to the front
    const savedIdx = filteredContacts.findIndex(c => c.id === result.contact?.id);
    if (savedIdx >= 0) {
      wheelIndex = savedIdx;
      renderWheel();
    }
  } catch (err) {
    console.error(err);
    showToast(err.message || 'Failed to save contact');
  }
}

function parseSocial(input) {
  if (!input.trim()) return {};
  // Simple parsing: "key: value, key2: value2"
  const obj = {};
  input.split(',').forEach(part => {
    const [key, value] = part.split(':').map(s => s.trim());
    if (key && value !== undefined) {
      obj[key] = value;
    }
  });
  return obj;
}

// ----- Delete Contact -----
async function handleDeleteContact() {
  if (!selectedContactId) return;
  if (!confirm('Delete this contact?')) return;
  
  try {
    const response = await fetch(`/api/v1/contacts/${selectedContactId}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error('Failed to delete');
    showToast('Contact deleted');
    await loadContacts();
    contactModal.close();
  } catch (err) {
    console.error(err);
    showToast('Failed to delete contact');
  }
}

// ----- Search & Filter -----
// Re-fetch so edits from other tabs or the vintage frontend show up
async function handleSearch() {
  currentSearchTerm = searchInput.value;
  await loadContacts();
}

function handleClearSearch() {
  searchInput.value = '';
  currentSearchTerm = '';
  loadContacts();
}

function handleFilterChange() {
  currentFilterTag = filterBySelect.value;
  loadContacts();
}

// ----- AI Features -----
// ----- Duplicates -----
async function handleDuplicates() {
  try {
    await loadDuplicates();
    duplicatesModal.showModal();
  } catch (err) {
    console.error(err);
    showToast('Duplicate check failed');
  }
}

async function loadDuplicates() {
  const response = await fetch('/api/v1/duplicates?threshold=0.7');
  if (!response.ok) throw new Error('Duplicate check failed');
  renderDuplicates(await response.json());
}

function renderDuplicates(duplicates) {
  duplicatesInfo.textContent = duplicates.length
    ? `${duplicates.length} ${duplicates.length === 1 ? 'pair' : 'pairs'} may be the same person. Merging keeps the contact you choose and fills its blanks from the other.`
    : 'No possible duplicates left.';
  duplicatesList.innerHTML = '';
  duplicates.forEach(dup => {
    const [a, b] = dup.contacts;
    const li = document.createElement('li');
    li.className = 'review-item';
    li.innerHTML = `
      <div class="review-item-main">
        <strong>${escapeHtml(a.name || 'Unnamed')}</strong> and <strong>${escapeHtml(b.name || 'Unnamed')}</strong>
        <div class="review-reasons">${escapeHtml(dup.reasons.join(', ') || 'similar')} · ${Math.round(dup.score * 100)}%</div>
      </div>
      <button type="button" class="small-btn">Review merge</button>`;
    li.querySelector('button').addEventListener('click', () => openMergeDialog(a, b));
    duplicatesList.appendChild(li);
  });
}

// ----- Import/Export -----
// Choosing a file previews it; nothing is written until the user confirms in the preview.
async function handleFileImport() {
  const file = fileInput.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/api/v1/import/preview', {
      method: 'POST',
      body: formData
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || 'Import failed');
    }
    pendingImportFile = file;
    renderImportPreview(await response.json());
    importModal.showModal();
  } catch (err) {
    console.error(err);
    showToast(err.message || 'Import failed');
    fileInput.value = '';
  }
}

function renderImportPreview({ rows, counts }) {
  const willImport = counts.new + counts.possible;
  importSummary.textContent = `${counts.total} in file: ${counts.new} new, ${counts.possible} sharing a name with an existing contact (imported), ${counts.skipped} skipped as already in your contacts.`;
  importConfirmBtn.textContent = `Import ${willImport}`;
  importConfirmBtn.disabled = willImport === 0;
  const labels = { new: 'New', possible: 'Check', skipped: 'Skipped' };
  importRows.innerHTML = '';
  rows.forEach(row => {
    const li = document.createElement('li');
    li.className = `review-item review-${row.status}`;
    const details = [row.phone, row.email].filter(Boolean).join(' · ');
    const note = [details, row.reason].filter(Boolean).join(' · ');
    li.innerHTML = `
      <div class="review-item-main">
        <strong>${escapeHtml(row.name || 'Unnamed')}</strong>
        <div class="review-reasons">${escapeHtml(note)}</div>
      </div>
      <span class="review-badge">${labels[row.status]}</span>`;
    importRows.appendChild(li);
  });
}

async function handleImportConfirm() {
  if (!pendingImportFile) return;

  const formData = new FormData();
  formData.append('file', pendingImportFile);
  importConfirmBtn.disabled = true;

  try {
    const response = await fetch('/api/v1/import', {
      method: 'POST',
      body: formData
    });
    if (!response.ok) throw new Error('Import failed');
    const result = await response.json();
    const skipped = result.skipped_duplicates ? `, skipped ${result.skipped_duplicates} already in your contacts` : '';
    showToast(`Imported ${result.new} new${skipped}`);
    importModal.close();
    await loadContacts();
  } catch (err) {
    console.error(err);
    showToast('Import failed');
  } finally {
    importConfirmBtn.disabled = false;
  }
}

// Clears the pending import on every close path (cancel, X, Escape)
function resetImportState() {
  pendingImportFile = null;
  fileInput.value = '';
}

async function handleExport() {
  // Simple export as JSON via /api/v1/bulk?action=export&format=json
  // For simplicity, we'll just fetch all contacts and create a download
  try {
    const response = await fetch('/api/v1/contacts');
    if (!response.ok) throw new Error('Failed to fetch contacts');
    const contacts = await response.json();
    const dataStr = JSON.stringify(contacts, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'rolodex_contacts.json';
    a.click();
    URL.revokeObjectURL(url);
    showToast('Contacts exported as JSON');
  } catch (err) {
    console.error(err);
    showToast('Export failed');
  }
}

// ----- Bulk Tag -----
async function handleBulkTagApply() {
  const tag = bulkTagInput.value.trim();
  if (!tag) {
    showToast('Please enter a tag');
    return;
  }
  if (selectedContacts.size === 0) {
    showToast('No contacts selected');
    return;
  }
  
  try {
    const response = await fetch('/api/v1/bulk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'tag',
        ids: Array.from(selectedContacts),
        tag
      })
    });
    if (!response.ok) throw new Error('Bulk tag failed');
    const result = await response.json();
    showToast(`Tagged ${result.tagged} contacts with "${tag}"`);
    bulkTagModal.close();
    selectedContacts.clear();
    await loadContacts();
  } catch (err) {
    console.error(err);
    showToast('Bulk tag failed');
  }
}

// ----- Merge -----
// Opens the merge dialog for two contacts; the user picks which one survives.
function openMergeDialog(a, b) {
  mergeContacts = [a, b];
  mergeInfo.textContent = 'Choose the contact to keep. Its details stay, blank fields are filled from the other, tags are combined and notes are appended.';
  mergeBody.innerHTML = '';
  [a, b].forEach((c, i) => {
    const col = document.createElement('label');
    col.className = 'merge-column';
    col.innerHTML = `
      <input type="radio" name="mergeKeep" value="${i}" ${i === 0 ? 'checked' : ''} />
      <h4>${escapeHtml(c.name || 'Unnamed')}</h4>
      <div>${escapeHtml(c.phone || '')}</div>
      <div>${escapeHtml(c.email || '')}</div>
      <div>${escapeHtml(c.address || '')}</div>
      <div class="review-reasons">${escapeHtml((c.tags || []).join(', '))}</div>`;
    mergeBody.appendChild(col);
  });
  mergeModal.showModal();
}

function resetMergeState() {
  mergeContacts = [];
  document.querySelectorAll('.selected-for-merge').forEach(el => el.classList.remove('selected-for-merge'));
}

async function handleMergeApply() {
  if (mergeContacts.length !== 2) {
    showToast('Please select two contacts to merge');
    return;
  }

  const keepIndex = Number(mergeBody.querySelector('input[name="mergeKeep"]:checked')?.value ?? 0);
  const [primary, secondary] = keepIndex === 0 ? mergeContacts : [mergeContacts[1], mergeContacts[0]];

  try {
    const response = await fetch('/api/v1/merge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        primary_id: primary.id,
        secondary_id: secondary.id,
        keep_existing: true,
        fields: ['name', 'phone', 'email', 'address', 'tags', 'notes', 'avatar', 'birthday', 'social', 'company', 'title']
      })
    });
    if (!response.ok) throw new Error('Merge failed');
    showToast(`Merged into ${primary.name || 'contact'}`);
    mergeModal.close();
    await loadContacts();
    if (duplicatesModal.open) await loadDuplicates();
  } catch (err) {
    console.error(err);
    showToast('Merge failed');
  }
}

// ----- UI Helpers -----
function showToast(message) {
  // Remove any existing toast
  const existing = document.getElementById('toast');
  if (existing) existing.remove();
  
  const toast = document.createElement('div');
  toast.id = 'toast';
  toast.textContent = message;
  toast.style.position = 'fixed';
  toast.style.bottom = '20px';
  toast.style.left = '50%';
  toast.style.transform = 'translateX(-50%)';
  toast.style.background = 'var(--bg-card)';
  toast.style.backdropFilter = 'blur(10px)';
  toast.style.color = 'var(--text-primary)';
  toast.style.padding = '12px 20px';
  toast.style.borderRadius = 'var(--border-radius)';
  toast.style.boxShadow = 'var(--shadow-md)';
  toast.style.zIndex = '1050';
  toast.style.opacity = '0';
  toast.style.pointerEvents = 'none';
  toast.style.transition = 'opacity 0.3s';
  
  document.body.appendChild(toast);
  requestAnimationFrame(() => {
    toast.style.opacity = '1';
  });
  
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Update counters
function updateCounters() {
  cardCountSpan.textContent = filteredContacts.length;
  totalCountSpan.textContent = contacts.length;
  
  // Update filter dropdown with current tags
  updateFilterDropdown();
}

function updateFilterDropdown() {
  const currentValue = filterBySelect.value;
  // Clear except first option
  while (filterBySelect.options.length > 1) {
    filterBySelect.remove(1);
  }
  // Collect unique tags
  const tagsSet = new Set();
  contacts.forEach(c => {
    (c.tags || []).forEach(tag => tagsSet.add(tag.toLowerCase()));
  });
  // Sort and add
  const sortedTags = Array.from(tagsSet).sort();
  sortedTags.forEach(tag => {
    const option = document.createElement('option');
    option.value = tag;
    option.textContent = tag.charAt(0).toUpperCase() + tag.slice(1);
    filterBySelect.appendChild(option);
  });
  // Restore selection if possible
  if (Array.from(filterBySelect.options).some(opt => opt.value === currentValue)) {
    filterBySelect.value = currentValue;
  }
}

// ----- Birthday Bar (simple implementation) -----
// "1990-10-15" is read as a local calendar date; new Date() would parse it as UTC midnight,
// which is the previous day in timezones west of UTC
function birthdayMonthDay(birthday) {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(birthday || '');
  if (m) return { month: +m[1] - 1, day: +m[2] };
  const d = new Date(birthday);
  return isNaN(d) ? null : { month: d.getMonth(), day: d.getDate() };
}

function updateBirthdayBar() {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const upcoming = contacts.map(c => ({ c, md: birthdayMonthDay(c.birthday) })).filter(({ md }) => {
    if (!md) return false;
    const next = new Date(today.getFullYear(), md.month, md.day);
    if (next < today) next.setFullYear(next.getFullYear() + 1);
    return Math.round((next - today) / 86400000) <= 7; // next 7 days, across month/year ends
  });

  if (upcoming.length === 0) {
    birthdayBar.style.display = 'none';
    return;
  }

  birthdayBar.style.display = 'block';
  birthdayBarContent.innerHTML = upcoming
    .map(({ c, md }) => `${escapeHtml(c.name)} (${md.month + 1}/${md.day})`)
    .join(' • ');
}

// Call updateBirthdayBar after loading calls
// We'll call it at the end of loadContacts and after any data changes
// Override loadOrig load to include birthday update
const originalLoadContacts = loadContacts;
loadContacts = async function() {
  await originalLoadContacts();
  updateBirthdayBar();
};
// Also call after loadContacts in applyFiltersAndSearch? We'll call after loadContacts anyway.
// Initialize Marked for markdown parsing
if (typeof marked === 'undefined') {
  console.warn('marked library not loaded, notes preview will not work');
}

// Expose some functions globally for console debugging
window.reloadContacts = loadContacts;
window.showToast = showToast;
// ── Reminders and activity log for the open contact ────────────────────

const contactExtras = document.getElementById('contactExtras');
const reminderList = document.getElementById('reminderList');
const activityList = document.getElementById('activityList');
let extrasContactId = null;

function extrasItem(text, actions) {
  const li = document.createElement('li');
  li.className = 'extras-item';
  const label = document.createElement('span');
  label.textContent = text;
  li.appendChild(label);
  for (const { label: actionLabel, onClick } of actions) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'extras-action';
    button.textContent = actionLabel;
    button.addEventListener('click', onClick);
    li.appendChild(button);
  }
  return li;
}

function fillExtrasList(list, items, emptyText) {
  list.innerHTML = '';
  if (!items.length) {
    const li = document.createElement('li');
    li.className = 'extras-empty';
    li.textContent = emptyText;
    list.appendChild(li);
    return;
  }
  items.forEach((item) => list.appendChild(item));
}

function reminderItem(r) {
  const text = `${r.completed ? 'Done: ' : ''}${r.title} (due ${r.due_date})`;
  const actions = [];
  if (!r.completed) actions.push({ label: 'Done', onClick: () => changeReminder(`/api/v1/reminders/${encodeURIComponent(r.id)}/complete`, 'POST') });
  actions.push({ label: 'Delete', onClick: () => changeReminder(`/api/v1/reminders/${encodeURIComponent(r.id)}`, 'DELETE') });
  return extrasItem(text, actions);
}

function activityItem(a) {
  return extrasItem(`${a.timestamp.slice(0, 10)} ${a.type}: ${a.subject}`, []);
}

function hideContactExtras() {
  extrasContactId = null;
  contactExtras.hidden = true;
}

async function loadContactExtras(contactId) {
  extrasContactId = contactId;
  contactExtras.hidden = false;
  const base = `/api/v1/contacts/${encodeURIComponent(contactId)}`;
  try {
    const [reminderRes, activityRes] = await Promise.all([fetch(`${base}/reminders`), fetch(`${base}/activities`)]);
    if (!reminderRes.ok || !activityRes.ok) throw new Error('load failed');
    const { reminders } = await reminderRes.json();
    const { activities } = await activityRes.json();
    if (extrasContactId !== contactId) return; // another contact was opened meanwhile
    fillExtrasList(reminderList, reminders.map(reminderItem), 'No reminders yet.');
    fillExtrasList(activityList, activities.map(activityItem), 'No activity logged yet.');
  } catch {
    showToast('Could not load reminders and activity');
  }
}

async function changeReminder(url, method) {
  const response = await fetch(url, { method });
  if (!response.ok) {
    showToast('Could not update reminder');
    return;
  }
  loadContactExtras(extrasContactId);
}

document.getElementById('reminderForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const title = document.getElementById('reminderTitle').value.trim();
  const dueDate = document.getElementById('reminderDue').value;
  if (!title || !dueDate || !extrasContactId) return;
  const response = await fetch(`/api/v1/contacts/${encodeURIComponent(extrasContactId)}/reminders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, due_date: dueDate }),
  });
  if (!response.ok) {
    showToast('Could not add reminder');
    return;
  }
  e.target.reset();
  loadContactExtras(extrasContactId);
});

document.getElementById('activityForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const type = document.getElementById('activityType').value;
  const subject = document.getElementById('activitySubject').value.trim();
  if (!subject || !extrasContactId) return;
  const response = await fetch(`/api/v1/contacts/${encodeURIComponent(extrasContactId)}/activities`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, subject, timestamp: new Date().toISOString() }),
  });
  if (!response.ok) {
    showToast('Could not log activity');
    return;
  }
  e.target.reset();
  loadContactExtras(extrasContactId);
});

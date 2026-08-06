// Global modal helper functions
let confirmCallback = null;
let dangerCallback = null;

function showValidationModal(message, title = 'Validation Error') {
    document.getElementById('validationModalTitle').innerHTML = `<i class="las la-exclamation-triangle me-1"></i> ${title}`;
    document.getElementById('validationModalBody').textContent = message;
    // Use getOrCreateInstance to prevent duplicate instances on rapid calls.
    bootstrap.Modal.getOrCreateInstance(document.getElementById('validationModal')).show();
}

function showSuccessModal(message, title = 'Success') {
    document.getElementById('successModalTitle').innerHTML = `<i class="las la-check-circle me-1"></i> ${title}`;
    document.getElementById('successModalBody').textContent = message;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('successModal')).show();
}

function showConfirmModal(message, title, callback) {
    document.getElementById('confirmModalTitle').innerHTML = `<i class="las la-question-circle me-1"></i> ${title}`;
    document.getElementById('confirmModalBody').textContent = message;
    confirmCallback = callback;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('confirmModal')).show();
}

function showDangerModal(message, title, callback) {
    document.getElementById('dangerModalTitle').innerHTML = `<i class="las la-exclamation-triangle me-1"></i> ${title}`;
    document.getElementById('dangerModalBody').textContent = message;
    dangerCallback = callback;
    bootstrap.Modal.getOrCreateInstance(document.getElementById('dangerModal')).show();
}

// Confirm button click handler
document.addEventListener('DOMContentLoaded', function() {
    const confirmBtn = document.getElementById('confirmModalBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', function() {
            if (confirmCallback) {
                confirmCallback();
            }
            bootstrap.Modal.getInstance(document.getElementById('confirmModal')).hide();
        });
    }

    const dangerBtn = document.getElementById('dangerModalBtn');
    if (dangerBtn) {
        dangerBtn.addEventListener('click', function() {
            if (dangerCallback) {
                dangerCallback();
            }
            bootstrap.Modal.getInstance(document.getElementById('dangerModal')).hide();
        });
    }

    // Clear stale callbacks when modals are dismissed (close X, backdrop click,
    // Escape key) so a subsequent modal open never fires the previous action.
    const confirmModal = document.getElementById('confirmModal');
    if (confirmModal) {
        confirmModal.addEventListener('hidden.bs.modal', function() {
            confirmCallback = null;
        });
    }

    const dangerModal = document.getElementById('dangerModal');
    if (dangerModal) {
        dangerModal.addEventListener('hidden.bs.modal', function() {
            dangerCallback = null;
        });
    }
});

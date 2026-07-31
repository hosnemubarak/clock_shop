// Global modal helper functions
let confirmCallback = null;
let dangerCallback = null;

function showValidationModal(message, title = 'Validation Error') {
    document.getElementById('validationModalTitle').innerHTML = `<i class="las la-exclamation-triangle me-1"></i> ${title}`;
    document.getElementById('validationModalBody').textContent = message;
    const modal = new bootstrap.Modal(document.getElementById('validationModal'));
    modal.show();
}

function showSuccessModal(message, title = 'Success') {
    document.getElementById('successModalTitle').innerHTML = `<i class="las la-check-circle me-1"></i> ${title}`;
    document.getElementById('successModalBody').textContent = message;
    const modal = new bootstrap.Modal(document.getElementById('successModal'));
    modal.show();
}

function showConfirmModal(message, title, callback) {
    document.getElementById('confirmModalTitle').innerHTML = `<i class="las la-question-circle me-1"></i> ${title}`;
    document.getElementById('confirmModalBody').textContent = message;
    confirmCallback = callback;
    const modal = new bootstrap.Modal(document.getElementById('confirmModal'));
    modal.show();
}

function showDangerModal(message, title, callback) {
    document.getElementById('dangerModalTitle').innerHTML = `<i class="las la-exclamation-triangle me-1"></i> ${title}`;
    document.getElementById('dangerModalBody').textContent = message;
    dangerCallback = callback;
    const modal = new bootstrap.Modal(document.getElementById('dangerModal'));
    modal.show();
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
});

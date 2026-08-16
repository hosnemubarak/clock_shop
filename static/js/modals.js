// Global modal compatibility API.
(function (window, document) {
    'use strict';

    var callbacks = { confirmModal: null, dangerModal: null };
    var triggers = new WeakMap();

    function byId(id) {
        return document.getElementById(id);
    }

    function modalInstance(root) {
        if (!root || !window.bootstrap || !window.bootstrap.Modal) return null;
        return window.bootstrap.Modal.getOrCreateInstance(root);
    }

    function setContent(modalId, message, title) {
        var root = byId(modalId);
        if (!root) return null;
        var titleNode = root.querySelector('[data-modal-title]');
        var body = byId(modalId + 'Body');
        if (titleNode) titleNode.textContent = title || '';
        if (body) body.textContent = message == null ? '' : String(message);
        return root;
    }

    function rememberTrigger(root) {
        if (root && document.activeElement && document.activeElement !== document.body) {
            triggers.set(root, document.activeElement);
        }
    }

    function showMessage(modalId, message, title) {
        var root = setContent(modalId, message, title);
        var instance = modalInstance(root);
        if (!instance) return false;
        rememberTrigger(root);
        instance.show();
        return true;
    }

    function showValidationModal(message, title) {
        return showMessage('validationModal', message, title || 'Validation Error');
    }

    function showSuccessModal(message, title) {
        return showMessage('successModal', message, title || 'Success');
    }

    function showConfirmModal(message, title, callback) {
        callbacks.confirmModal = typeof callback === 'function' ? callback : null;
        return showMessage('confirmModal', message, title || 'Confirm Action');
    }

    function showDangerModal(message, title, callback) {
        callbacks.dangerModal = typeof callback === 'function' ? callback : null;
        return showMessage('dangerModal', message, title || 'Confirm Action');
    }

    function showModalError(target, message) {
        var node = typeof target === 'string' ? byId(target) : target;
        if (!node) return false;
        node.textContent = message == null ? '' : String(message);
        node.hidden = false;
        node.classList.remove('d-none');
        node.setAttribute('role', 'alert');
        return true;
    }

    function clearModalError(target) {
        var node = typeof target === 'string' ? byId(target) : target;
        if (!node) return;
        node.textContent = '';
        node.hidden = true;
        node.classList.add('d-none');
    }

    function bindAction(modalId, buttonId) {
        var root = byId(modalId);
        var button = byId(buttonId);
        if (!root || !button) return;
        button.addEventListener('click', function () {
            var callback = callbacks[modalId];
            callbacks[modalId] = null;
            if (callback) callback();
            var instance = modalInstance(root);
            if (instance) instance.hide();
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        bindAction('confirmModal', 'confirmModalBtn');
        bindAction('dangerModal', 'dangerModalBtn');

        ['validationModal', 'successModal', 'confirmModal', 'dangerModal'].forEach(function (modalId) {
            var root = byId(modalId);
            if (!root) return;
            root.addEventListener('hidden.bs.modal', function () {
                if (Object.prototype.hasOwnProperty.call(callbacks, modalId)) callbacks[modalId] = null;
                var trigger = triggers.get(root);
                triggers.delete(root);
                if (trigger && trigger.isConnected && typeof trigger.focus === 'function') trigger.focus();
            });
        });

        var paymentModal = document.querySelector('[data-payment-success-modal]');
        if (paymentModal) {
            modalInstance(paymentModal).show();
            var url = new URL(window.location.href);
            url.searchParams.delete('print_payment');
            window.history.replaceState({}, document.title, url.toString());
        }
    });

    window.showValidationModal = showValidationModal;
    window.showSuccessModal = showSuccessModal;
    window.showConfirmModal = showConfirmModal;
    window.showDangerModal = showDangerModal;
    window.showModalError = showModalError;
    window.clearModalError = clearModalError;
})(window, document);

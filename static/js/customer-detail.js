(function (window, document) {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var modal = document.getElementById('openingBalanceModal');
        var form = document.getElementById('openingBalanceForm');
        if (!modal || !form || !window.bootstrap || !window.bootstrap.Modal) return;

        var instance = window.bootstrap.Modal.getOrCreateInstance(modal);
        var submit = document.getElementById('openingBalanceSubmit');
        var submitLabel = submit.querySelector('[data-submit-label]');
        var errorBox = document.getElementById('openingBalanceError');
        var openingBalance = document.querySelector('[data-customer-opening-balance]');
        var openingBalanceDate = document.querySelector('[data-customer-opening-balance-date]');
        var totalDue = document.querySelector('[data-customer-total-due]');
        var currencySymbol = form.dataset.currencySymbol || '';
        var fields = {
            opening_balance: document.getElementById('id_opening_balance'),
            opening_balance_date: document.getElementById('id_opening_balance_date')
        };

        function clearErrors() {
            window.clearModalError(errorBox);
            Object.keys(fields).forEach(function (name) {
                var error = modal.querySelector('[data-field-error="' + name + '"]');
                if (error) window.clearModalError(error);
                if (fields[name]) fields[name].classList.remove('is-invalid');
            });
        }

        function showErrors(errors) {
            clearErrors();
            var summary = [];
            Object.keys(errors || {}).forEach(function (name) {
                var messages = errors[name] || [];
                if (name === '__all__') {
                    summary = summary.concat(messages);
                    return;
                }
                var error = modal.querySelector('[data-field-error="' + name + '"]');
                if (error) window.showModalError(error, messages.join(' '));
                if (fields[name]) fields[name].classList.add('is-invalid');
            });
            if (summary.length) window.showModalError(errorBox, summary.join(' '));
            else if (!Object.keys(errors || {}).length) window.showModalError(errorBox, 'The opening balance could not be saved.');
        }

        modal.addEventListener('show.bs.modal', function () {
            form.reset();
            clearErrors();
        });
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            clearErrors();
            submit.disabled = true;
            submitLabel.textContent = 'Saving...';
            fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                credentials: 'same-origin',
                headers: {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'}
            }).then(function (response) {
                var type = response.headers.get('content-type') || '';
                if (!type.includes('application/json')) throw new Error('Unexpected server response.');
                return response.json().then(function (payload) {
                    if (!response.ok) {
                        showErrors(payload.errors || {'__all__': [payload.message || 'The opening balance could not be saved.']});
                        throw new Error('validation');
                    }
                    return payload;
                });
            }).then(function (payload) {
                if (payload.status !== 'success') throw new Error('The server did not confirm the update.');
                if (openingBalance) openingBalance.textContent = currencySymbol + payload.opening_balance;
                if (openingBalanceDate) openingBalanceDate.textContent = payload.opening_balance_date;
                if (totalDue) totalDue.textContent = currencySymbol + payload.total_due;
                instance.hide();
                window.location.reload();
            }).catch(function (error) {
                if (error.message !== 'validation') showErrors({'__all__': [error.message || 'Unable to save the opening balance.']});
            }).finally(function () {
                submit.disabled = false;
                submitLabel.textContent = 'Save';
            });
        });
    });
})(window, document);

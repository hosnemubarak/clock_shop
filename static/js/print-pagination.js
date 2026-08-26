(function () {
    'use strict';

    var source = document.querySelector('.invoice-paper');
    var sourceTable = source && source.querySelector('[data-print-items]');
    var fullHeader = source && source.querySelector('[data-print-full-header]');
    if (!source || !sourceTable || !fullHeader) {
        return;
    }

    var printPages = document.createElement('div');
    printPages.className = 'print-pages';
    printPages.setAttribute('aria-hidden', 'true');
    document.body.appendChild(printPages);

    var preparing = false;
    var preparationToken = 0;
    var assetsReady = false;
    var assetsPromise = null;

    function clone(selector) {
        var element = source.querySelector(selector);
        return element ? element.cloneNode(true) : null;
    }

    function appendClone(parent, selector) {
        var element = clone(selector);
        if (element) {
            parent.appendChild(element);
        }
    }

    function createPage(isFirstPage, includeTable) {
        var sheet = document.createElement('section');
        sheet.className = 'print-page';

        var content = document.createElement('div');
        content.className = 'print-page-content';
        sheet.appendChild(content);

        appendClone(sheet, '.watermark');
        appendClone(content, '[data-print-full-header]');
        if (isFirstPage) {
            appendClone(content, '.doc-type-banner');
            appendClone(content, '.invoice-info');
            appendClone(content, '[data-print-document-title]');
        }

        var body = null;
        if (includeTable !== false) {
            var table = sourceTable.cloneNode(false);
            var sourceHead = sourceTable.querySelector('thead');
            if (sourceHead) {
                var head = sourceHead.cloneNode(true);
                table.appendChild(head);
            }
            body = document.createElement('tbody');
            table.appendChild(body);
            content.appendChild(table);
        }

        var pageNumber = document.createElement('div');
        pageNumber.className = 'print-page-number';
        pageNumber.setAttribute('data-print-page-label', '');
        sheet.appendChild(pageNumber);

        printPages.appendChild(sheet);
        return { sheet: sheet, content: content, body: body };
    }

    function pageFits(page) {
        return page.content.scrollHeight <= page.content.clientHeight + 1;
    }

    function appendRows() {
        var currentPage = createPage(true);
        var rows = sourceTable.querySelectorAll('tbody > tr');

        Array.prototype.forEach.call(rows, function (sourceRow) {
            var row = sourceRow.cloneNode(true);
            currentPage.body.appendChild(row);

            if (!pageFits(currentPage) && currentPage.body.children.length > 1) {
                currentPage.body.removeChild(row);
                currentPage = createPage(false);
                currentPage.body.appendChild(row);
            }
        });

        return currentPage;
    }

    function appendFinalContent(page) {
        var finalContent = document.createElement('div');
        finalContent.className = 'print-final-content';
        appendClone(finalContent, '.totals');
        appendClone(finalContent, '.bottom-content');
        page.content.appendChild(finalContent);

        if (!pageFits(page)) {
            page.content.removeChild(finalContent);
            page = createPage(false, false);
            page.content.appendChild(finalContent);
        }

        if (pageFits(page)) {
            return;
        }

        page.content.removeChild(finalContent);
        var totals = clone('.totals');
        if (totals) {
            page.content.appendChild(totals);
        }

        var bottomSource = source.querySelector('.bottom-content');
        var bottom = document.createElement('div');
        bottom.className = 'bottom-content';
        page.content.appendChild(bottom);

        if (!bottomSource) {
            return;
        }

        Array.prototype.forEach.call(bottomSource.children, function (sourceSection) {
            var section = sourceSection.cloneNode(true);
            bottom.appendChild(section);
            if (!pageFits(page)) {
                bottom.removeChild(section);
                page = createPage(false, false);
                bottom = document.createElement('div');
                bottom.className = 'bottom-content';
                page.content.appendChild(bottom);
                bottom.appendChild(section);
            }
        });
    }

    function buildPages(token) {
        if (token !== preparationToken) {
            return;
        }

        printPages.innerHTML = '';
        printPages.classList.add('is-measuring');
        var finalPage = appendRows();
        appendFinalContent(finalPage);

        var pages = printPages.querySelectorAll('.print-page');
        Array.prototype.forEach.call(pages, function (page, index) {
            var label = page.querySelector('[data-print-page-label]');
            label.textContent = pages.length > 1 ? 'Page ' + (index + 1) + ' of ' + pages.length : '';
        });

        printPages.classList.remove('is-measuring');
        printPages.classList.add('is-ready');
        document.body.classList.add('print-pagination-ready');
        preparing = false;
    }

    function waitForAssets() {
        if (assetsPromise) {
            return assetsPromise;
        }
        var fonts = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
        var images = Array.prototype.map.call(document.images, function (image) {
            if (image.complete) {
                return Promise.resolve();
            }
            return new Promise(function (resolve) {
                image.addEventListener('load', resolve, { once: true });
                image.addEventListener('error', resolve, { once: true });
            });
        });
        assetsPromise = Promise.all([fonts].concat(images)).then(function () {
            assetsReady = true;
        });
        return assetsPromise;
    }

    function preparePrint() {
        if (preparing) {
            return;
        }
        preparing = true;
        preparationToken += 1;
        var token = preparationToken;
        if (assetsReady) {
            buildPages(token);
            return;
        }
        waitForAssets().then(function () {
            buildPages(token);
        });
    }

    function printDocument() {
        waitForAssets().then(function () {
            preparationToken += 1;
            buildPages(preparationToken);
            window.requestAnimationFrame(function () {
                window.print();
            });
        });
    }

    window.addEventListener('beforeprint', preparePrint);
    window.addEventListener('afterprint', function () {
        preparing = false;
        document.body.classList.remove('print-pagination-ready');
    });
    window.printInvoiceDocument = printDocument;
}());

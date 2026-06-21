/**
 * ==========================================================================
 *  SIMKOS EXPORT UTILITIES - Versi 3.0
 *  Export Excel & PDF dengan DataTables API, Kop Surat, Baris Ringkasan
 *  yang TEPAT SEJAJAR di kolom nominal yang benar.
 * ==========================================================================
 *
 *  CARA PAKAI DI SETIAP HALAMAN:
 *
 *  1. Include di vendor_js:
 *     <script src="{% static 'js/simkos_export.js' %}"></script>
 *
 *  2. Definisikan variabel konfigurasi:
 *     var EXCEL_INFO = { name, address, phone, email, copyright };
 *     var PDF_INFO   = { name, address, phone, email, copyright };
 *     // FOOTER_DATA: key = indeks kolom DataTables (0-based, termasuk kolom Aksi),
 *     //              value = nominal ANGKA (akan diformat otomatis menjadi Rp)
 *     var FOOTER_DATA  = { 3: 5000000 };   // total di kolom indeks ke-3
 *     var FOOTER_LABEL = 'RINGKASAN (10 Tagihan | Belum: 3 | Lunas: 7)';
 *
 *  3. Panggil fungsi:
 *     function exportToExcel() { SimkosExport.buildExcel('#tabelId', EXCEL_INFO, FOOTER_DATA, FOOTER_LABEL, 'JUDUL', 'NamaFile'); }
 *     function exportToPDF()   { SimkosExport.buildPDF('#tabelId', PDF_INFO,   FOOTER_DATA, FOOTER_LABEL, 'JUDUL', 'NamaFile'); }
 *     function toggleColumns() { SimkosExport.toggleColumns('#tabelId'); }
 *
 * ==========================================================================
 */

var SimkosExport = (function () {
    'use strict';

    // ── DETEKSI MOBILE WEBVIEW ────────────────────────────────────────────
    /**
     * Cek apakah berjalan di dalam WebView (Capacitor / Android WebView / iOS WKWebView).
     * Di WebView, Blob URL + link.click() TIDAK berfungsi untuk download file.
     * @returns {boolean}
     */
    function _isWebView() {
        var ua = navigator.userAgent || '';
        // Capacitor menambahkan bridge
        if (window.Capacitor) return true;
        // SerpApp bridge terdaftar di WebView
        if (window.SerpApp) return true;
        // Android WebView
        if (/wv|WebView/i.test(ua)) return true;
        // Generic Android in-app browser
        if (/Android.*Version\/[\d.]+/i.test(ua) && !/Chrome\/[\d.]+/i.test(ua)) return true;
        // iOS WKWebView (bukan Safari standalone)
        if (/iPhone|iPad|iPod/i.test(ua) && !/Safari/i.test(ua)) return true;
        return false;
    }

    // ── KIRIM KE ANDROID VIA NATIVE BRIDGE (CHUNKING) ────────────────────
    /**
     * Kirim data Base64 ke Android native via SerpApp bridge.
     * Menggunakan chunking untuk file besar agar tidak crash.
     */
    function _sendToSerpApp(pureBase64, fname, mimeType) {
        if (!window.SerpApp) return false;
        if (window.SerpApp.saveBase64Chunk) {
            console.log('[SimkosExport] Mengirim via Async Chunking:', fname, '(' + pureBase64.length + ' chars)');
            var chunkSize = 65536;
            var i = 0;
            function sendNext() {
                if (i < pureBase64.length) {
                    window.SerpApp.saveBase64Chunk(pureBase64.substring(i, i + chunkSize));
                    i += chunkSize;
                    setTimeout(sendNext, 5);
                } else {
                    window.SerpApp.finishBase64Chunk(fname, mimeType);
                }
            }
            sendNext();
        } else if (window.SerpApp.saveBase64) {
            window.SerpApp.saveBase64(pureBase64, fname, mimeType);
        }
        return true;
    }

    // ── UNIVERSAL FILE DOWNLOAD ──────────────────────────────────────────
    /**
     * Download file dari Blob — kompatibel browser biasa DAN WebView.
     *
     * Strategi (berurutan, paling reliable lebih dulu):
     * 1. Delegasi ke window._downloadBlob (dari master.html inline) jika tersedia
     * 2. WebView + SerpApp → konversi Blob ke Base64 → kirim via native bridge
     * 3. WebView fallback → navigator.share() atau overlay manual
     * 4. Browser biasa → createObjectURL + link.click() (standar)
     *
     * @param {Blob}   blob     - File data dalam bentuk Blob
     * @param {string} filename - Nama file dengan ekstensi
     */
    function _downloadBlob(blob, filename) {
        // Prioritas 1: Delegasi ke master.html yang punya Prototype-Level Intercept
        if (window._downloadBlob && window._downloadBlob !== _downloadBlob) {
            console.log('[SimkosExport] Delegasi ke window._downloadBlob (master.html)');
            window._downloadBlob(blob, filename);
            return;
        }

        if (_isWebView()) {
            _downloadBlobWebView(blob, filename);
        } else {
            _downloadBlobBrowser(blob, filename);
        }
    }

    /**
     * Download di WebView — PRIORITAS UTAMA: SerpApp native bridge.
     * Mengkonversi Blob ke Base64, lalu kirim ke Android native via chunking.
     * Fallback ke navigator.share() atau overlay jika SerpApp tidak tersedia.
     */
    function _downloadBlobWebView(blob, filename) {
        // Strategi 1 (PALING RELIABLE): SerpApp native bridge
        if (window.SerpApp) {
            console.log('[SimkosExport] Menggunakan SerpApp bridge untuk download:', filename);
            var reader = new FileReader();
            reader.onloadend = function() {
                var base64data = reader.result;
                var pureBase64 = base64data.split(',')[1];
                if (pureBase64) {
                    _sendToSerpApp(pureBase64, filename, blob.type || 'application/octet-stream');
                }
            };
            reader.readAsDataURL(blob);
            return;
        }

        // Strategi 2: navigator.share() — Native Android Share Sheet
        if (navigator.share && navigator.canShare) {
            try {
                var file = new File([blob], filename, { type: blob.type });
                var shareData = { files: [file], title: filename };

                if (navigator.canShare(shareData)) {
                    navigator.share(shareData)
                        .then(function() {
                            console.log('File berhasil di-share/download via native share');
                        })
                        .catch(function(err) {
                            if (err.name !== 'AbortError') {
                                console.warn('Share gagal, mencoba fallback:', err);
                                _showManualDownloadLink(blob, filename);
                            }
                        });
                    return;
                }
            } catch (e) {
                console.warn('navigator.share error:', e);
            }
        }

        // Strategi 3: Overlay manual download
        _showManualDownloadLink(blob, filename);
    }

    /**
     * Download di browser biasa menggunakan Blob URL + link.click().
     */
    function _downloadBlobBrowser(blob, filename) {
        try {
            var url = URL.createObjectURL(blob);
            var link = document.createElement('a');
            link.href = url;
            link.download = filename;
            link.style.display = 'none';
            document.body.appendChild(link);
            link.click();
            setTimeout(function () {
                document.body.removeChild(link);
                URL.revokeObjectURL(url);
            }, 300);
        } catch (e) {
            console.error('Download browser gagal:', e);
            _showManualDownloadLink(blob, filename);
        }
    }

    /**
     * Tampilkan overlay premium dengan link download manual.
     * User tap tombol download secara langsung (bukan programmatic) —
     * ini membuat <a download> bekerja bahkan di beberapa WebView.
     *
     * @param {Blob}   blob     - Blob data untuk di-download
     * @param {string} filename - Nama file
     */
    function _showManualDownloadLink(blob, filename) {
        var blobUrl = URL.createObjectURL(blob);

        var overlay = document.createElement('div');
        overlay.className = 'download-overlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:99999;display:flex;align-items:center;justify-content:center;padding:20px;';
        overlay.innerHTML =
            '<div style="background:#fff;border-radius:16px;padding:28px 24px;text-align:center;max-width:360px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,0.3);">' +
                '<div style="width:60px;height:60px;margin:0 auto 16px;background:linear-gradient(135deg,#e8e8ff,#d0d0ff);border-radius:50%;display:flex;align-items:center;justify-content:center;">' +
                    '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#696cff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' +
                '</div>' +
                '<h5 style="margin:0 0 8px;color:#333;font-size:1.1rem;font-weight:700;">File Siap Diunduh</h5>' +
                '<p style="color:#697a8d;font-size:0.85rem;margin-bottom:20px;line-height:1.4;">Ketuk tombol di bawah untuk menyimpan file <strong>' + filename + '</strong></p>' +
                '<a id="_dl_link" href="' + blobUrl + '" download="' + filename + '" ' +
                    'style="display:block;background:linear-gradient(135deg,#696cff,#5f61e6);color:#fff;padding:14px 24px;border-radius:10px;text-decoration:none;font-weight:600;font-size:0.95rem;margin-bottom:12px;">' +
                    '📥 Download ' + filename +
                '</a>' +
                '<button id="_dl_close" style="background:none;border:none;color:#697a8d;cursor:pointer;font-size:0.8rem;padding:8px 16px;">Tutup</button>' +
            '</div>';

        overlay.querySelector('#_dl_close').addEventListener('click', function () {
            overlay.remove();
            URL.revokeObjectURL(blobUrl);
        });
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) {
                overlay.remove();
                URL.revokeObjectURL(blobUrl);
            }
        });
        overlay.querySelector('#_dl_link').addEventListener('click', function () {
            setTimeout(function () {
                overlay.remove();
                setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 5000);
            }, 1000);
        });

        document.body.appendChild(overlay);
    }

    // ── FORMAT RUPIAH ─────────────────────────────────────────────────────────
    /**
     * Format angka menjadi string Rupiah Indonesia.
     * Contoh: 10400000 → "Rp 10.400.000"
     * @param {number|string} value
     * @returns {string}
     */
    function _formatRupiah(value) {
        var num = parseFloat(String(value).replace(/[^\d.-]/g, ''));
        if (isNaN(num)) return String(value); // biarkan apa adanya jika bukan angka
        return 'Rp ' + num.toLocaleString('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    }

    /**
     * Format angka biasa (tanpa prefix Rp).
     * Contoh: 11 → "11", 1500 → "1.500"
     * @param {number|string} value
     * @returns {string}
     */
    function _formatNumber(value) {
        var num = parseFloat(String(value).replace(/[^\d.-]/g, ''));
        if (isNaN(num)) return String(value);
        return num.toLocaleString('id-ID', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    }

    /**
     * Cek apakah nilai tampak seperti nominal uang (bisa berisi "Rp", titik, koma, angka)
     * Angka 0 dianggap valid!
     * @param {string} str
     * @returns {boolean}
     */
    function _isMoneyLike(str) {
        var s = String(str).trim();
        return /^(Rp[\s\.]?)?[\d.,]+$/.test(s) || s === '0';
    }

    /**
     * Cek apakah kolom tertentu adalah kolom nominal uang.
     * @param {number}      colIdx       - Indeks kolom DataTables
     * @param {Array|null}  moneyColumns - Array indeks kolom yang merupakan nominal uang. Null=semua dianggap uang.
     * @returns {boolean}
     */
    function _isMoneyColumn(colIdx, moneyColumns) {
        if (!moneyColumns || !Array.isArray(moneyColumns)) return true; // default: semua diformat Rp (backward compatible)
        return moneyColumns.indexOf(colIdx) !== -1;
    }

    /**
     * Format nilai footer sesuai tipe kolom (uang atau angka biasa).
     * @param {*}           rawVal       - Nilai mentah
     * @param {number}      colIdx       - Indeks kolom
     * @param {Array|null}  moneyColumns - Kolom mana yang nominal uang
     * @returns {string}
     */
    function _formatFooterValue(rawVal, colIdx, moneyColumns) {
        var str = String(rawVal);
        if (_isMoneyColumn(colIdx, moneyColumns)) {
            return _isMoneyLike(str) ? _formatRupiah(rawVal) : str;
        } else {
            // Bukan kolom uang — tampilkan sebagai angka biasa tanpa Rp
            return _isMoneyLike(str) ? _formatNumber(rawVal) : str;
        }
    }

    // ── TOGGLE KOLOM ─────────────────────────────────────────────────────────
    /**
     * Toggle visibility kolom DataTable berdasarkan checkbox .column-checkbox.
     * Menggunakan new $.fn.dataTable.Api() agar TIDAK re-initialize tabel.
     * @param {string} tableId - Selector ID tabel, mis: '#pembayaranTable'
     */
    function toggleColumns(tableId) {
        if (typeof $ === 'undefined' || typeof $.fn.dataTable === 'undefined') {
            console.error('SimkosExport: jQuery DataTables belum dimuat!');
            return;
        }
        try {
            var tableApi = new $.fn.dataTable.Api(tableId);
            document.querySelectorAll('.column-checkbox').forEach(function (cb) {
                tableApi.column(parseInt(cb.value)).visible(cb.checked);
            });
        } catch (e) {
            console.error('SimkosExport.toggleColumns error:', e);
        }
    }

    // ── AMBIL KOLOM VISIBLE ───────────────────────────────────────────────────
    /**
     * Ambil daftar kolom yang visible dari DataTable (kecuali kolom "Aksi").
     * @param {string} tableId
     * @returns {Array} [{index, text}]
     */
    function _getVisibleColumns(tableId) {
        var tableApi = new $.fn.dataTable.Api(tableId);
        var cols = [];
        tableApi.columns().every(function (index) {
            var headerNode = this.header();
            var headerText = headerNode ? headerNode.textContent.trim() : '';
            var lowerText = headerText.toLowerCase();
            // Skip kolom "Aksi", "Action", "Tindakan", atau header kosong dari export
            var isActionCol = (lowerText === 'aksi' || lowerText === 'action' || lowerText === 'tindakan' || lowerText === '');
            if (this.visible() && !isActionCol) {
                cols.push({ index: index, text: headerText });
            }
        });
        return cols;
    }

    // ── BANGUN BARIS RINGKASAN EXCEL ──────────────────────────────────────────
    /**
     * Bangun array sel baris ringkasan untuk Excel.
     * Algoritma:
     *  - Scan visibleColumns dari kiri ke kanan
     *  - Jika colIdx ada di footerData → tampilkan total (format Rupiah HANYA jika termasuk moneyColumns)
     *  - Jika tidak → kumpulkan kolom berurutan, jadikan satu colspan
     *                 Kolom span pertama (paling kiri) tampilkan footerLabel
     *
     * @param {Array}      visibleColumns - [{index, text}]
     * @param {Object}     footerData     - { colIdx: nilaiTotal } (colIdx = indeks DataTables asli)
     * @param {string}     footerLabel    - Teks label ringkasan
     * @param {Array|null} moneyColumns   - Indeks kolom yang merupakan nominal uang (Rp). Null=semua.
     * @returns {Array} [{text, span}]
     */
    function _buildSummaryRowExcel(visibleColumns, footerData, footerLabel, moneyColumns) {
        var cells = [];
        var labelPlaced = false;
        var ri = 0;

        while (ri < visibleColumns.length) {
            var colIdx = visibleColumns[ri].index;

            if (footerData && footerData[colIdx] !== undefined && footerData[colIdx] !== null && footerData[colIdx] !== '') {
                // Kolom ini punya total — format sesuai tipe (uang atau angka biasa)
                var rawVal = footerData[colIdx];
                var formatted = _formatFooterValue(rawVal, colIdx, moneyColumns);
                cells.push({ text: formatted, span: 1, align: 'right', isTotal: true });
                ri++;
            } else {
                // Kumpulkan kolom berurutan yang tidak punya total
                var spanCount = 0;
                var si = ri;
                while (
                    si < visibleColumns.length &&
                    (!footerData || footerData[visibleColumns[si].index] === undefined ||
                        footerData[visibleColumns[si].index] === null ||
                        footerData[visibleColumns[si].index] === '')
                ) {
                    spanCount++;
                    si++;
                }
                var label = !labelPlaced ? (footerLabel || 'RINGKASAN') : '';
                if (!labelPlaced && label) labelPlaced = true;
                cells.push({ text: label, span: spanCount, align: 'left', isTotal: false });
                ri += spanCount;
            }
        }
        return cells;
    }

    // ── BANGUN BARIS RINGKASAN PDF ────────────────────────────────────────────
    /**
     * Bangun array sel baris ringkasan untuk pdfMake.
     * @param {Array}      visibleColumns
     * @param {Object}     footerData
     * @param {string}     footerLabel
     * @param {Array|null} moneyColumns - Indeks kolom yang merupakan nominal uang (Rp). Null=semua.
     * @returns {Array} array pdfMake cell objects
     */
    function _buildSummaryRowPDF(visibleColumns, footerData, footerLabel, moneyColumns) {
        var summaryRow = [];
        var labelPlaced = false;
        var ri = 0;

        while (ri < visibleColumns.length) {
            var colIdx = visibleColumns[ri].index;

            if (footerData && footerData[colIdx] !== undefined && footerData[colIdx] !== null && footerData[colIdx] !== '') {
                var rawVal = footerData[colIdx];
                var formatted = _formatFooterValue(rawVal, colIdx, moneyColumns);
                summaryRow.push({
                    text: formatted,
                    bold: true,
                    fillColor: '#EEF0FF',
                    color: '#4B4EE6',
                    alignment: 'right'
                });
                ri++;
            } else {
                var spanCount = 0;
                var si = ri;
                while (
                    si < visibleColumns.length &&
                    (!footerData || footerData[visibleColumns[si].index] === undefined ||
                        footerData[visibleColumns[si].index] === null ||
                        footerData[visibleColumns[si].index] === '')
                ) {
                    spanCount++;
                    si++;
                }
                var label = !labelPlaced ? (footerLabel || 'RINGKASAN') : '';
                if (!labelPlaced && label) labelPlaced = true;

                var cell = {
                    text: label,
                    bold: true,
                    fillColor: '#EEF0FF',
                    color: '#5F61E6',
                    alignment: 'left'
                };
                if (spanCount > 1) {
                    cell.colSpan = spanCount;
                }
                summaryRow.push(cell);
                // Tambah sel kosong untuk colspan
                for (var k = 1; k < spanCount; k++) {
                    summaryRow.push({ text: '', fillColor: '#EEF0FF' });
                }
                ri += spanCount;
            }
        }
        return summaryRow;
    }

    // ── EXPORT EXCEL ──────────────────────────────────────────────────────────
    /**
     * Export data tabel ke file Excel (.xls) dengan kop surat perusahaan dan baris ringkasan.
     *
     * @param {string} tableId     - Selector tabel, mis: '#pembayaranTable'
     * @param {Object} info        - { name, address, phone, email, copyright }
     * @param {Object} footerData  - { colIdx: nilaiTotal } — indeks kolom DataTables asli
     * @param {string} footerLabel - Label ringkasan (mis: 'RINGKASAN (10 Tagihan)')
     * @param {string} title       - Judul dokumen
     * @param {string} filename    - Nama file tanpa ekstensi
     * @param {Array}  [moneyColumns] - Opsional. Indeks kolom yang merupakan nominal uang (format Rp).
     *                                 Jika tidak diberikan, SEMUA kolom numerik diformat Rp (backward compatible).
     */
    function buildExcel(tableId, info, footerData, footerLabel, title, filename, moneyColumns) {
        try {
            var tableEl = document.querySelector(tableId);
            if (!tableEl) { alert('Tabel tidak ditemukan!'); return; }
            if (typeof $ === 'undefined' || typeof $.fn.dataTable === 'undefined') {
                alert('DataTables belum dimuat!'); return;
            }

            var visibleColumns = _getVisibleColumns(tableId);
            var tableApi = new $.fn.dataTable.Api(tableId);
            var colCount = visibleColumns.length;

            if (colCount === 0) { alert('Tidak ada kolom yang tersedia untuk di-export!'); return; }

            var html = '<html xmlns:o="urn:schemas-microsoft-com:office:office"'
                + ' xmlns:x="urn:schemas-microsoft-com:office:excel"'
                + ' xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="utf-8">'
                + '<style>table{border-collapse:collapse;} th,td{font-family:Arial,sans-serif;font-size:9pt;}'
                + '.kop-judul{font-size:14pt;font-weight:bold;color:#5F61E6;}'
                + '.kop-info{font-size:9pt;color:#697A8D;}'
                + '.th-header{background-color:#696CFF;color:#FFFFFF;font-weight:bold;padding:6px;}'
                + '.td-data{padding:4px 6px;}'
                + '.td-summary{background-color:#EEF0FF;font-weight:bold;padding:4px 6px;color:#4B4EE6;}'
                + '.td-label{background-color:#EEF0FF;font-weight:bold;padding:4px 6px;color:#5F61E6;}'
                + '</style></head><body>';

            // ── KOP SURAT ──
            html += '<table border="0" style="margin-bottom:8px;width:100%;">';
            html += '<tr><td colspan="' + colCount + '" style="text-align:center;font-size:16pt;font-weight:bold;color:#5F61E6;border:none;">' + (info.name || 'SIMKOS') + '</td></tr>';
            html += '<tr><td colspan="' + colCount + '" style="text-align:center;font-size:9pt;color:#697A8D;border:none;">' + (info.address || '') + '</td></tr>';
            html += '<tr><td colspan="' + colCount + '" style="text-align:center;font-size:9pt;color:#697A8D;border:none;">Telp: ' + (info.phone || '-') + ' | Email: ' + (info.email || '-') + '</td></tr>';
            html += '<tr><td colspan="' + colCount + '" style="border:none;">&nbsp;</td></tr>';
            html += '</table>';

            // ── JUDUL & TANGGAL ──
            html += '<table border="0" style="margin-bottom:6px;">';
            html += '<tr><td colspan="' + colCount + '" style="font-size:12pt;font-weight:bold;color:#5F61E6;border:none;">' + (title || 'Laporan') + '</td></tr>';
            html += '<tr><td colspan="' + colCount + '" style="font-size:8pt;color:#697A8D;border:none;">Tanggal: '
                + new Date().toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' }) + '</td></tr>';
            html += '<tr><td colspan="' + colCount + '" style="border:none;">&nbsp;</td></tr>';
            html += '</table>';

            // ── TABEL DATA ──
            html += '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;width:100%;">';

            // Header
            html += '<thead><tr>';
            visibleColumns.forEach(function (col) {
                html += '<th style="background-color:#696CFF;color:#FFFFFF;font-weight:bold;padding:6px;white-space:nowrap;border:1px solid #DBDADE;">' + col.text + '</th>';
            });
            html += '</tr></thead><tbody>';

            // Baris data — SEMUA baris yang lolos filter DataTables (bukan hanya halaman aktif)
            // search:'applied' = hormati filter pencarian tapi export semua halaman
            tableApi.rows({ search: 'applied' }).every(function (rowIdx) {
                html += '<tr>';
                visibleColumns.forEach(function (col) {
                    var cellNode = tableApi.cell(rowIdx, col.index).node();
                    var text = cellNode ? cellNode.textContent.trim().replace(/\s+/g, ' ') : '';
                    var isRight = /^Rp[\s]/.test(text) || /^[\d.,]+$/.test(text);
                    html += '<td style="padding:4px 6px;border:1px solid #DBDADE;' + (isRight ? 'text-align:right;' : '') + '">' + text + '</td>';
                });
                html += '</tr>';
            });

            // ── BARIS RINGKASAN ──
            var hasFooter = footerData && Object.keys(footerData).length > 0;
            var summaryCells = _buildSummaryRowExcel(visibleColumns, hasFooter ? footerData : {}, footerLabel, moneyColumns);
            html += '<tr>';
            summaryCells.forEach(function (cell) {
                var style = cell.isTotal
                    ? 'background-color:#EEF0FF;font-weight:bold;color:#4B4EE6;text-align:right;padding:5px 6px;border:1px solid #DBDADE;'
                    : 'background-color:#EEF0FF;font-weight:bold;color:#5F61E6;text-align:left;padding:5px 6px;border:1px solid #DBDADE;';
                if (cell.span > 1) {
                    html += '<td colspan="' + cell.span + '" style="' + style + '">' + cell.text + '</td>';
                } else {
                    html += '<td style="' + style + '">' + cell.text + '</td>';
                }
            });
            html += '</tr>';

            html += '</tbody></table>';

            // ── FOOTER ──
            html += '<table border="0" style="margin-top:8px;width:100%;">';
            html += '<tr>';
            html += '<td style="font-size:8pt;color:#697A8D;border:none;">Dicetak pada: ' + new Date().toLocaleString('id-ID') + '</td>';
            html += '<td style="font-size:8pt;color:#697A8D;text-align:right;border:none;">' + (info.copyright || '') + '</td>';
            html += '</tr></table>';

            html += '</body></html>';

            var blob = new Blob(['\uFEFF' + html], { type: 'application/vnd.ms-excel;charset=utf-8' });
            var exportFilename = (filename || 'Export') + '_' + new Date().toISOString().slice(0, 10) + '.xls';
            _downloadBlob(blob, exportFilename);

        } catch (err) {
            console.error('SimkosExport.buildExcel error:', err);
            alert('Terjadi kesalahan saat export Excel: ' + err.message);
        }
    }

    // ── EXPORT PDF ────────────────────────────────────────────────────────────
    /**
     * Export data tabel ke PDF menggunakan pdfMake, dengan kop surat dan baris ringkasan.
     *
     * @param {string} tableId     - Selector tabel
     * @param {Object} info        - { name, address, phone, email, copyright }
     * @param {Object} footerData  - { colIdx: nilaiTotal }
     * @param {string} footerLabel - Label ringkasan
     * @param {string} title       - Judul dokumen
     * @param {string} filename    - Nama file tanpa ekstensi
     * @param {Array}  [moneyColumns] - Opsional. Indeks kolom yang merupakan nominal uang (format Rp).
     */
    function buildPDF(tableId, info, footerData, footerLabel, title, filename, moneyColumns) {
        try {
            if (typeof pdfMake === 'undefined') {
                alert('pdfMake library tidak tersedia! Pastikan pdfmake.min.js sudah dimuat.');
                return;
            }
            var tableEl = document.querySelector(tableId);
            if (!tableEl) { alert('Tabel tidak ditemukan!'); return; }

            var visibleColumns = _getVisibleColumns(tableId);
            var tableApi = new $.fn.dataTable.Api(tableId);
            var colCount = visibleColumns.length;

            if (colCount === 0) { alert('Tidak ada kolom yang tersedia untuk di-export!'); return; }

            // ── HEADER KOLOM ──
            var headers = visibleColumns.map(function (col) {
                return {
                    text: col.text,
                    style: 'tableHeader',
                    fillColor: '#696CFF',
                    color: '#FFFFFF',
                    bold: true,
                    alignment: 'center'
                };
            });

            // ── DATA BARIS — semua baris yang lolos filter (bukan hanya halaman aktif) ──
            var body = [headers];
            tableApi.rows({ search: 'applied' }).every(function (rowIdx) {
                var row = [];
                visibleColumns.forEach(function (col) {
                    var cellNode = tableApi.cell(rowIdx, col.index).node();
                    var text = cellNode ? cellNode.textContent.trim().replace(/\s+/g, ' ') : '';
                    if (text.length > 80) { text = text.substring(0, 77) + '...'; }
                    // Alignment kanan untuk kolom yang mengandung "Rp" atau angka
                    var isRightAlign = /^Rp[\s]/.test(text) || /^[\d.,]+$/.test(text);
                    row.push({ text: text, alignment: isRightAlign ? 'right' : 'left' });
                });
                if (row.length > 0) body.push(row);
            });

            // ── BARIS RINGKASAN ──
            var hasFooter = footerData && Object.keys(footerData).length > 0;
            var summaryRow = _buildSummaryRowPDF(visibleColumns, hasFooter ? footerData : {}, footerLabel, moneyColumns);
            if (summaryRow.length > 0) body.push(summaryRow);

            // ── HITUNG LEBAR KOLOM ──
            // Auto widths agar pdfMake menghitung otomatis berdasarkan konten
            var colWidths = Array(colCount).fill('auto');

            var bodyLength = body.length;

            var docDefinition = {
                pageOrientation: 'landscape',
                pageSize: 'A4',
                pageMargins: [30, 110, 30, 55],

                // ── KOP SURAT DI HEADER PDF ──
                header: function (currentPage) {
                    return {
                        margin: [30, 12, 30, 0],
                        table: {
                            widths: ['*', 80],
                            body: [[
                                {
                                    border: [false, false, false, true],
                                    stack: [
                                        { text: info.name || 'SIMKOS', style: 'companyName' },
                                        { text: info.address || '', style: 'companyInfo' },
                                        { text: 'Telp: ' + (info.phone || '-') + ' | Email: ' + (info.email || '-'), style: 'companyInfo' }
                                    ]
                                },
                                {
                                    border: [false, false, false, true],
                                    stack: [
                                        { text: 'Hal. ' + currentPage, style: 'pageNumber', alignment: 'right' }
                                    ]
                                }
                            ]]
                        },
                        layout: {
                            hLineWidth: function (i, node) { return (i === node.table.body.length) ? 1 : 0; },
                            vLineWidth: function () { return 0; },
                            hLineColor: function () { return '#696CFF'; }
                        }
                    };
                },

                content: [
                    { text: title || 'Laporan', style: 'documentTitle', margin: [0, 0, 0, 2] },
                    {
                        text: 'Tanggal: ' + new Date().toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' }),
                        style: 'dateText',
                        margin: [0, 0, 0, 10]
                    },
                    {
                        table: {
                            headerRows: 1,
                            dontBreakRows: true,
                            widths: colWidths,
                            body: body
                        },
                        layout: {
                            fillColor: function (rowIndex) {
                                if (rowIndex === 0) return '#696CFF';            // Header biru
                                if (rowIndex === bodyLength - 1) return '#EEF0FF'; // Ringkasan biru muda
                                return (rowIndex % 2 === 0) ? '#F5F5F9' : null;    // Zebra stripe
                            },
                            hLineWidth: function () { return 0.5; },
                            vLineWidth: function () { return 0.5; },
                            hLineColor: function () { return '#DBDADE'; },
                            vLineColor: function () { return '#DBDADE'; },
                            paddingLeft: function () { return 4; },
                            paddingRight: function () { return 4; },
                            paddingTop: function () { return 3; },
                            paddingBottom: function () { return 3; }
                        }
                    }
                ],

                // ── FOOTER PDF ──
                footer: function (currentPage, pageCount) {
                    return {
                        margin: [30, 8, 30, 0],
                        columns: [
                            { text: 'Dicetak pada: ' + new Date().toLocaleString('id-ID'), style: 'footerText' },
                            {
                                text: (info.copyright || '') + '  |  Halaman ' + currentPage + ' dari ' + pageCount,
                                style: 'footerText',
                                alignment: 'right'
                            }
                        ]
                    };
                },

                styles: {
                    companyName:   { fontSize: 13, bold: true, color: '#5F61E6' },
                    companyInfo:   { fontSize: 8,  color: '#697A8D' },
                    pageNumber:    { fontSize: 8,  color: '#697A8D' },
                    documentTitle: { fontSize: 14, bold: true, color: '#5F61E6' },
                    dateText:      { fontSize: 9,  color: '#697A8D' },
                    tableHeader:   { bold: true, fontSize: 8, color: '#FFFFFF' },
                    footerText:    { fontSize: 7,  color: '#697A8D' }
                },
                defaultStyle: { fontSize: 7 }
            };

            var pdfFilename = (filename || 'Export') + '_' + new Date().toISOString().slice(0, 10) + '.pdf';
            var pdfDoc = pdfMake.createPdf(docDefinition);

            // Di WebView, pdfMake.download() tidak berfungsi.
            // Gunakan getBlob() lalu _downloadBlob() sebagai fallback.
            if (_isWebView()) {
                pdfDoc.getBlob(function(blob) {
                    _downloadBlob(blob, pdfFilename);
                });
            } else {
                pdfDoc.download(pdfFilename);
            }

        } catch (err) {
            console.error('SimkosExport.buildPDF error:', err);
            alert('Terjadi kesalahan saat export PDF: ' + err.message);
        }
    }

    // ── PUBLIC API ────────────────────────────────────────────────────────────
    return {
        toggleColumns: toggleColumns,
        buildExcel:    buildExcel,
        buildPDF:      buildPDF,
        formatRupiah:  _formatRupiah   // expose untuk penggunaan di halaman jika perlu
    };

})();

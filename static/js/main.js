(function () {
    'use strict';

    var form      = document.getElementById('date-filter-form');
    var inputFrom = document.getElementById('date-from');
    var inputTo   = document.getElementById('date-to');

    if (!form || !inputFrom || !inputTo) { return; }

    function formatDate(d) {
        return d.getFullYear() + '-'
            + String(d.getMonth() + 1).padStart(2, '0') + '-'
            + String(d.getDate()).padStart(2, '0');
    }

    function getPresetRanges() {
        var today = new Date();
        today.setHours(0, 0, 0, 0);
        var todayStr = formatDate(today);

        // ISO Monday: (getDay() + 6) % 7 gives days since Monday (Sun=6, Mon=0)
        var monday = new Date(today);
        monday.setDate(today.getDate() - (today.getDay() + 6) % 7);

        var monthStart     = new Date(today.getFullYear(), today.getMonth(), 1);
        var lastMonthStart = new Date(today.getFullYear(), today.getMonth() - 1, 1);
        var lastMonthEnd   = new Date(today.getFullYear(), today.getMonth(), 0); // day 0 = last of prev month

        return {
            'all':        { from: '',                         to: ''                        },
            'week':       { from: formatDate(monday),         to: todayStr                  },
            'month':      { from: formatDate(monthStart),     to: todayStr                  },
            'last-month': { from: formatDate(lastMonthStart), to: formatDate(lastMonthEnd)  }
        };
    }

    function markActivePreset() {
        var ranges = getPresetRanges();
        document.querySelectorAll('.preset-btn').forEach(function (btn) {
            var r = ranges[btn.dataset.preset];
            btn.classList.toggle('active', !!(r && r.from === inputFrom.value && r.to === inputTo.value));
        });
    }

    document.querySelectorAll('.preset-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var r = getPresetRanges()[btn.dataset.preset];
            if (!r) { return; }
            inputFrom.value = r.from;
            inputTo.value   = r.to;
            form.submit();
        });
    });

    markActivePreset();
}());

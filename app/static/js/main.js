function coming() {
    showInfo("Coming soon!");
}

function toast(msg, type) {
    $.bootstrapGrowl(msg, {
        ele: 'body', // which element to append to
        type: type, // (null, 'info', 'danger', 'success')
        offset: {from: 'top', amount: 20}, // 'top', or 'bottom'
        align: 'right', // ('left', 'right', or 'center')
        width: 500, // (integer, or 'auto')
        delay: 5000, // Time while the message will be displayed. It's not equivalent to the *demo* timeOut!
        allow_dismiss: false, // If true then will display a cross to close the popup.
        stackup_spacing: 10 // spacing between consecutively stacked growls.
    });
}

function showError(msg) {
    toast(msg, 'danger');
}

function showInfo(msg) {
    toast(msg, 'info');
}

function showSuccess(msg) {
    toast(msg, 'success');
}

// HTML encode/decode
Html = {
    nl2br: function (a) {
        if (!a) return "";
        return a.replace(/\n/gim, "<br />");
    },
    br2nl: function (a) {
        if (!a) return "";
        return a.replace(/<br \/>/g, '\n').replace(/<br>/g, '\n').replace(/<br\/>/g, '\n');
    }
};

// Install scroll-to-top
$(function () {
    /* Scroll to top */
    $(window).scroll(function () {
        ( $(this).scrollTop() > 300 ) ? $("a#scroll-to-top").addClass('visible') : $("a#scroll-to-top").removeClass('visible');
    });

    $("a#scroll-to-top").click(function () {
        $("html, body").animate({scrollTop: 0}, "slow");
        return false;
    });
});
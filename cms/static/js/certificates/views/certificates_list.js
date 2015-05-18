// Backbone Application View: Certificates List

define([
    'js/views/list', 'js/certificates/views/certificate_item', 'gettext'
], function(ListView, CertificateItemView, gettext) {
    'use strict';
    var CertificatesListView = ListView.extend({
        tagName: 'div',
        className: 'certificates-list',
        newModelOptions: {},

        // Translators: this refers to a collection of certificates.
        itemCategoryDisplayName: gettext('certificate'),

        // Translators: This line refers to the initial state of the form when no data has been inserted
        emptyMessage: gettext('You have not created any certificates yet.'),

        createItemView: function(options) {
            // Returns either an editor view or a details view, depending on context
            return new CertificateItemView(options);
        }
    });
    return CertificatesListView;
});

// Backbone Application View: Signatory Editor

define(['js/views/utils/view_utils', "js/views/feedback_prompt", "js/views/feedback_notification", "js/models/uploads",
    "js/views/uploads", 'js/utils/templates', 'underscore', 'jquery', 'gettext'],
function(ViewUtils, PromptView, NotificationView, FileUploadModel, FileUploadDialog, TemplateUtils, _, $, gettext) {
    'use strict';
    var SignatoryEditorView = Backbone.View.extend({
        tagName: 'div',
        events: {
            'change .signatory-name-input': 'setSignatoryName',
            'change .signatory-title-input': 'setSignatoryTitle',
            'change .signatory-signature-inputt': 'setSignatorySignatureImagePath',
            'click .signatory-panel-delete': 'deleteItem',
            'click .action-upload-signature': 'uploadSignatureImage'
        },

        className: function () {
            // Determine the CSS class names for this model instance
            var index = this.getModelIndex(this.model);
            return [
                'signatory-edit',
                'signatory-edit-view-' + index
            ].join(' ');
        },

        initialize: function(options) {
            // Set up the initial state of the attributes set for this model instance
             _.bindAll(this, 'render');
            this.model.bind('change', this.render);
            this.eventAgg = options.eventAgg;
            this.isEditingAllCollections = options.isEditingAllCollections;
            this.template = this.loadTemplate('signatory-editor');
        },

        getModelIndex: function(givenModel) {
            // Retrieve the position of this model in its collection
            return this.model.collection.indexOf(givenModel);
        },

        loadTemplate: function(name) {
            // Retrieve the corresponding template for this model
            return TemplateUtils.loadTemplate(name);
        },

        getTotalSignatoriesOnServer: function() {
            // Retrieve the count of signatories stored server-side
            var count = 0;
            this.model.collection.each(function( modelSignatory) {
                if(!modelSignatory.isNew()) {
                    count ++;
                }
            });
            return count;
        },

        render: function() {
            // Assemble the editor view for this model
            var attributes = $.extend({}, this.model.attributes, {
                signatory_number: this.getModelIndex(this.model) + 1,
                signatories_count: this.model.collection.length,
                isNew: this.model.isNew(),
                is_editing_all_collections: this.isEditingAllCollections,
                total_saved_signatories: this.getTotalSignatoriesOnServer()
            });

            return $(this.el).html(this.template(attributes));
        },

        setSignatoryName: function(event) {
            // Update the model with the provided data
            if (event && event.preventDefault) { event.preventDefault(); }
            this.model.set(
                'name',
                this.$('.signatory-name-input').val(),
                { silent: true }
            );
        },

        setSignatoryTitle: function(event) {
            // Update the model with the provided data
            if (event && event.preventDefault) { event.preventDefault(); }
            this.model.set(
                'title',
                this.$('.signatory-title-input').val(),
                { silent: true }
            );
        },

        setSignatorySignatureImagePath: function(event) {
            // #TODO should have a single method for setting these fields.
            if (event && event.preventDefault) { event.preventDefault(); }
            this.model.set(
                'signature_image_path',
                this.$('.signatory-signature-input').val(),
                { silent: true }
            );
        },

        deleteItem: function(event) {
            // Remove the specified model from the collection
            if (event && event.preventDefault) { event.preventDefault(); }
            var certificate = this.model.get('certificate');
            var model = this.model;
            var self = this;
            var confirm = new PromptView.Warning({
                title: gettext('Are you sure you want to delete this signatory with title "'+model.get('title') +'"?'),
                message: gettext('This action cannot be undone.'),
                actions: {
                    primary: {
                        text: gettext('OK'),
                        click: function () {
                            var deleting = new NotificationView.Mini({
                                title: gettext('Deleting')
                            });
                            if (model.isNew()){
                                model.collection.remove(model);
                                self.eventAgg.trigger("onSignatoryRemoved", model);
                            }
                            else {
                                deleting.show();
                                // delete signature image
                                $.ajax({
                                    url: CMS.URL.UPLOAD_ASSET + model.get('signature_image_path'),
                                    type: 'DELETE',
                                    dataType: 'json',
                                    contentType: 'application/json',
                                    data: {},
                                    success: function (data) {}
                                });

                                model.destroy({
                                    wait: true,
                                    success: function (model, response) {
                                        deleting.hide();
                                        self.eventAgg.trigger("onSignatoryRemoved", model);
                                    }
                                });
                            }
                            confirm.hide();
                        }
                    },
                    secondary: {
                        text: gettext('Cancel'),
                        click: function() {
                            confirm.hide();
                        }
                    }
                }
            });
            confirm.show();
        },

        uploadSignatureImage: function(event) {
            event.preventDefault();
            var upload = new FileUploadModel({
                title: gettext("Upload your signature image."),
                message: gettext("Image must be 450px X 150px transparent PNG."),
                mimeTypes: ['image/png']
            });
            var self = this;
            var modal = new FileUploadDialog({
                model: upload,
                onSuccess: function(response) {
                    self.model.set('signature_image_path', response.asset.url);
                }
            });
            modal.show();
        }
    });
    return SignatoryEditorView;
});

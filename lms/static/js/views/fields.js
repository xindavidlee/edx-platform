;(function (define, undefined) {
    'use strict';
    define([
        'gettext', 'jquery', 'underscore', 'backbone', 'js/mustache', 'backbone-super'
    ], function (gettext, $, _, Backbone, RequireMustache) {

        var Mustache = window.Mustache || RequireMustache;

        var messageRevertDelay = 4000;
        var FieldViews = {};

        FieldViews.FieldView = Backbone.View.extend({

            fieldType: 'generic',

            className: function () {
                return 'u-field' + ' u-field-' + this.fieldType + ' u-field-' + this.options.valueAttribute;
            },

            tagName: 'div',

            indicators: {
                'error': '<i class="fa fa-exclamation-triangle message-error"></i>',
                'validationError': '<i class="fa fa-exclamation-triangle message-validation-error"></i>',
                'inProgress': '<i class="fa fa-spinner message-in-progress"></i>',
                'success': '<i class="fa fa-check message-success"></i>'
            },

            messages: {
                'error': gettext('An error occurred. Please try again.'),
                'validationError': '',
                'inProgress': gettext('Saving'),
                'success': gettext('Your changes have been saved.')
            },

            initialize: function (options) {

                this.template = _.template($(this.templateSelector).text()),

                this.helpMessage = this.options.helpMessage || '';
                this.showMessages = _.isUndefined(this.options.showMessages) ? true : this.options.showMessages;

                _.bindAll(this, 'modelValue', 'saveAttributes', 'saveSucceeded', 'getMessage',
                    'message', 'showHelpMessage', 'showInProgressMessage', 'showSuccessMessage', 'showErrorMessage');
            },

            modelValue: function () {
                return this.model.get(this.options.valueAttribute);
            },

            saveAttributes: function (attributes, options) {
                var view = this;
                var defaultOptions = {
                    contentType: 'application/merge-patch+json',
                    patch: true,
                    wait: true,
                    success: function (model, response, options) {
                        view.saveSucceeded()
                    },
                    error: function (model, xhr, options) {
                        view.showErrorMessage(xhr)
                    }
                };
                this.showInProgressMessage();
                this.model.save(attributes, _.extend(defaultOptions, options));
            },

            saveSucceeded: function () {
                this.showSuccessMessage();
            },

            message: function (message) {
                return this.$('.u-field-message').html(message);
            },

            getMessage: function(message_status) {
                if ((message_status + 'Message') in this) {
                    return this[message_status + 'Message'].call(this);
                } else if (this.showMessages) {
                    return this.indicators[message_status] + this.messages[message_status];
                }
                return this.indicators[message_status];
            },

            showHelpMessage: function () {
                this.message(this.helpMessage);
            },

            showInProgressMessage: function () {
                this.message(this.getMessage('inProgress'));
            },

            showSuccessMessage: function () {
                var successMessage = this.getMessage('success');
                this.message(successMessage);

                if (this.options.refreshPageOnSave) {
                    document.location.reload();
                }

                var view = this;

                var context = Date.now();
                this.lastSuccessMessageContext = context;

                setTimeout(function () {
                    if ((context === view.lastSuccessMessageContext) && (view.message().html() == successMessage)) {
                        view.showHelpMessage();
                    }
                }, messageRevertDelay);
            },

            showErrorMessage: function (xhr) {
                if (xhr.status === 400) {
                    try {
                        var errors = JSON.parse(xhr.responseText);
                        var validationErrorMessage = Mustache.escapeHtml(errors['field_errors'][this.options.valueAttribute]['user_message']);
                        var message = this.indicators['validationError'] + validationErrorMessage;
                        this.message(message);
                    } catch (error) {
                        this.message(this.getMessage('error'));
                    }
                } else {
                    this.message(this.getMessage('error'));
                }
            }
        });

        FieldViews.ReadonlyFieldView = FieldViews.FieldView.extend({

            fieldType: 'readonly',

            templateSelector: '#field_readonly-tpl',

            initialize: function (options) {
                this._super(options);
                _.bindAll(this, 'render', 'fieldValue', 'updateValueInField');
                this.listenTo(this.model, "change:" + this.options.valueAttribute, this.updateValueInField);
            },

            render: function () {
                this.$el.html(this.template({
                    id: this.options.valueAttribute,
                    title: this.options.title,
                    value: this.modelValue(),
                    message: this.helpMessage
                }));
                return this;
            },

            fieldValue: function () {
                return this.$('.u-field-value input').val();
            },

            updateValueInField: function () {
                this.$('.u-field-value input').val(Mustache.escapeHtml(this.modelValue()));
            }
        });

        FieldViews.TextFieldView = FieldViews.FieldView.extend({

            fieldType: 'text',

            templateSelector: '#field_text-tpl',

            events: {
                'change input': 'saveValue'
            },

            initialize: function (options) {
                this._super(options);
                _.bindAll(this, 'render', 'fieldValue', 'updateValueInField', 'saveValue');
                this.listenTo(this.model, "change:" + this.options.valueAttribute, this.updateValueInField);
            },

            render: function () {
                this.$el.html(this.template({
                    id: this.options.valueAttribute,
                    title: this.options.title,
                    value: this.modelValue(),
                    message: this.helpMessage
                }));
                return this;
            },

            fieldValue: function () {
                return this.$('.u-field-value input').val();
            },

            updateValueInField: function () {
                var value = (_.isUndefined(this.modelValue()) || _.isNull(this.modelValue())) ? '' : this.modelValue();
                this.$('.u-field-value input').val(Mustache.escapeHtml(value));
            },

            saveValue: function (event) {
                var attributes = {};
                attributes[this.options.valueAttribute] = this.fieldValue();
                this.saveAttributes(attributes);
            }
        });

        FieldViews.DropdownFieldView = FieldViews.FieldView.extend({

            fieldType: 'dropdown',

            templateSelector: '#field_dropdown-tpl',

            events: {
                'change select': 'saveValue'
            },

            initialize: function (options) {
                this._super(options);
                _.bindAll(this, 'render', 'fieldValue', 'updateValueInField', 'saveValue');
                this.listenTo(this.model, "change:" + this.options.valueAttribute, this.updateValueInField);
            },

            render: function () {
                this.$el.html(this.template({
                    id: this.options.valueAttribute,
                    title: this.options.title,
                    required: this.options.required,
                    selectOptions: this.options.options,
                    message: this.helpMessage,
                }));
                this.updateValueInField()
                return this;
            },

            fieldValue: function () {
                return this.$('.u-field-value select').val();
            },

            updateValueInField: function () {
                var value = (_.isUndefined(this.modelValue()) || _.isNull(this.modelValue())) ? '' : this.modelValue();
                this.$('.u-field-value select').val(Mustache.escapeHtml(value));
            },

            saveValue: function () {
                var attributes = {};
                attributes[this.options.valueAttribute] = this.fieldValue();
                this.saveAttributes(attributes);
            }
        });

        FieldViews.LinkFieldView = FieldViews.FieldView.extend({

            fieldType: 'link',

            templateSelector: '#field_link-tpl',

            events: {
                'click a': 'linkClicked'
            },

            initialize: function (options) {
                this._super(options);
                _.bindAll(this, 'render', 'linkClicked');
            },

            render: function () {
                this.$el.html(this.template({
                    id: this.options.valueAttribute,
                    title: this.options.title,
                    linkTitle: this.options.linkTitle,
                    linkHref: this.options.linkHref,
                    message: this.helpMessage,
                }));
                return this;
            },

            linkClicked: function () {
                event.preventDefault();
            }
        });

        return FieldViews;
    })
}).call(this, define || RequireJS.define);
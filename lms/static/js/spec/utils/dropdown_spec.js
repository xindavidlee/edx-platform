define([
    'jquery', 'logger'
], function($, Logger) {
    'use strict';

    describe('Dropdown Menus', function() {

        describe('constructor', function() {
            describe('always', function() {
                var wrapper, button, menu, menu_item, menu_action;

                beforeEach(function() {
                    loadFixtures('js/fixtures/utils/dropdown.html');
                    wrapper = $('.wrapper-more-actions');
                    button = wrapper.children('.button-more.has-dropdown');
                    menu = wrapper.children('.dropdown-menu');
                    menu_item = menu.children('.dropdown-item');
                    menu_action = menu_item.children('.action');
                });

                it('adds the dropdown menus', function() {
                    // If a button with the class 'has-dropdown' is present...
                    if (button.length > 0) {
                        // We should expect the following to be true.
                        expect(wrapper.length).toBe(button.length);
                        expect(menu.length).toBe(wrapper.length);
                        expect(menu_item.length).toBeGreaterThan(0);
                        expect(menu_action.length).toBe(menu_item.length);
                    }
                });

                it('ensures ARIA attributes are present on button and menu', function() {
                    expect(button).toHaveAttrs({
                        'aria-haspopup': 'true',
                        'aria-expanded': 'false',
                        'aria-controls'
                    });

                    expect(menu).toHaveAttrs({
                        // Programmatic focus assignment
                        'tabindex': '-1'
                    });
                });
            });

            describe('when running', function() {
                var wrapper, button, menu, menu_item, menu_action, KEY = $.ui.keyCode,

                    keyPressEvent = function(key) {
                        return $.Event('keydown', { keyCode: key });
                    };

                beforeEach(function() {
                    loadFixtures('js/fixtures/utils/dropdown.html');
                    wrapper = $('.wrapper-more-actions');
                    button = wrapper.children('.button-more.has-dropdown');
                    menu = wrapper.children('.dropdown-menu');
                    menu_item = menu.children('.dropdown-item');
                    menu_action = menu_item.children('.action');
                    spyOn($.fn, 'focus').andCallThrough();
                });

                it('opens the menu on button click', function() {
                    button.click();
                    expect(button).toHaveClass('is-active');
                    expect(button).toHaveAttrs({
                        'aria-expanded': 'true'
                    });
                    expect(menu).toHaveClass('is-visible');
                });

                it('closes the menu on outside click', function() {
                    $(window).click();
                    expect(button).not.toHaveClass('is-active');
                    expect(button).toHaveAttrs({
                        'aria-expanded': 'false'
                    });
                    expect(menu).not.toHaveClass('is-visible');
                    expect(menu).toHaveClass('is-hidden');
                });

                it('opens the menu on ENTER kepress', function() {
                    button.trigger(keyPressEvent(KEY.ENTER));
                    expect(button).toHaveClass('is-active');
                    expect(button).toHaveAttrs({
                        'aria-expanded': 'true'
                    });
                    expect(menu).toHaveClass('is-visible');
                    expect(menu.focus).toHaveBeenCalled();
                });

                it('opens the menu on SPACE kepress', function() {
                    button.trigger(keyPressEvent(KEY.SPACE));
                    expect(button).toHaveClass('is-active');
                    expect(button).toHaveAttrs({
                        'aria-expanded': 'true'
                    });
                    expect(menu).toHaveClass('is-visible');
                    expect(menu.focus).toHaveBeenCalled();
                });

                it('closes the menu on ESC keypress', function() {
                    $(window).trigger(keyPressEvent(KEY.ESC));
                    expect(button).not.toHaveClass('is-active');
                    expect(button).toHaveAttrs({
                        'aria-expanded': 'false'
                    });
                    expect(menu).not.toHaveClass('is-visible');
                    expect(menu).toHaveClass('is-hidden');
                });
            });
        });
    });
}).call(this);
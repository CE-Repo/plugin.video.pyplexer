# -*- coding: utf-8 -*-

import pyxbmct.addonwindow as pyxbmct  # pylint: disable=import-error
import xbmc  # pylint: disable=import-error
import xbmcgui  # pylint: disable=import-error

from core.constants import CONFIG
from core.logger import Logger
from core.strings import i18n

LOG = Logger('plex_signin')
DIALOG = xbmcgui.Dialog()


class AlreadyActiveException(Exception):
    pass


# noinspection PyAttributeOutsideInit
class PlexManage(pyxbmct.AddonFullWindow):  # pylint: disable=too-many-instance-attributes
    def __init__(self, title='', window=None):
        """Class constructor"""
        # Call the base class' constructor.
        super(PlexManage, self).__init__(title)  # pylint: disable=super-with-arguments
        # Set width, height and the grid parameters
        self.setGeometry(800, 400, 9, 21)
        # Call set controls method
        self.set_controls()
        # Call set navigation method.
        self.set_navigation()
        # Connect Backspace button to close our addon.
        self.connect(pyxbmct.ACTION_NAV_BACK, self.close)
        self.context = None
        self.window = window

    def __enter__(self):
        if self.window.getProperty('-'.join([CONFIG['id'], 'dialog_active'])) == 'true':
            raise AlreadyActiveException
        self.window.setProperty('-'.join([CONFIG['id'], 'dialog_active']), 'true')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.window.clearProperty('-'.join([CONFIG['id'], 'dialog_active']))

    def start(self):
        xbmc.executebuiltin('Dialog.Close(all,true)')
        self.gather_plex_information()
        self.setFocus(self.cancel_button)
        self.doModal()

    def gather_plex_information(self):
        user = self.context.plex_network.get_myplex_information()

        self.name_field.addLabel(user['username'])
        self.email_field.addLabel(user['email'])
        self.plexpass_field.addLabel(user['plexpass'])
        self.membersince_field.addLabel(user['membersince'])
        if user['thumb']:
            self.thumb.setImage(user['thumb'])

    def set_context(self, context):
        self.context = context

    def set_controls(self):
        """Set up UI controls"""
        # Description Text
        self.description = pyxbmct.TextBox()
        self.placeControl(self.description, 2, 0, columnspan=4)

        # Username label
        self.name_label = pyxbmct.Label('[B]%s[/B]' % i18n('Username:'), alignment=1)
        self.placeControl(self.name_label, 1, 3, columnspan=4)
        # username fade label
        self.name_field = pyxbmct.FadeLabel()
        self.placeControl(self.name_field, 1, 7, columnspan=8)

        # thumb label
        self.thumb = pyxbmct.Image('', aspectRatio=2)
        self.placeControl(self.thumb, 1, 15, rowspan=2, columnspan=2)

        # Email Label
        self.email_label = pyxbmct.Label('[B]%s[/B]' % i18n('Email:'), alignment=1)
        self.placeControl(self.email_label, 2, 3, columnspan=4)
        # Email fade label
        self.email_field = pyxbmct.FadeLabel()
        self.placeControl(self.email_field, 2, 7, columnspan=8)

        # plexpass Label
        self.plexpass_label = pyxbmct.Label('[B]%s[/B]' % i18n('Plex Pass:'), alignment=1)
        self.placeControl(self.plexpass_label, 3, 3, columnspan=4)
        # Password columnspan=4
        self.plexpass_field = pyxbmct.FadeLabel()
        self.placeControl(self.plexpass_field, 3, 7, columnspan=8)

        # Member since Label
        self.membersince_label = pyxbmct.Label('[B]%s[/B]' % i18n('Joined:'), alignment=1)
        self.placeControl(self.membersince_label, 4, 3, columnspan=4)
        # Member since fade label
        self.membersince_field = pyxbmct.FadeLabel()
        self.placeControl(self.membersince_field, 4, 7, columnspan=8)

        # Cancel button
        self.cancel_button = pyxbmct.Button(i18n('Exit'))
        self.placeControl(self.cancel_button, 6, 4, columnspan=4, rowspan=2)
        # Cancel button closes window

        # Switch button
        self.switch_button = pyxbmct.Button(i18n('Switch User'))
        self.placeControl(self.switch_button, 6, 8, columnspan=5, rowspan=2)

        # Signout button
        self.signout_button = pyxbmct.Button(i18n('Sign Out'))
        self.placeControl(self.signout_button, 6, 13, columnspan=4, rowspan=2)

        # Submit button to get token
        self.connect(self.cancel_button, self.close)
        self.connect(self.switch_button, lambda: self.switch())  # pylint: disable=unnecessary-lambda
        self.connect(self.signout_button, lambda: self.signout())  # pylint: disable=unnecessary-lambda

    def switch(self):
        switched = switch_user(self.context, refresh=False)
        if switched:
            self.close()

    def signout(self):
        sign_out(self.context, refresh=False)
        if not self.context.plex_network.is_myplex_signedin():
            self.close()

    def set_navigation(self):
        """Set up keyboard/remote navigation between controls."""
        self.cancel_button.setNavigation(self.switch_button, self.signout_button,
                                         self.signout_button, self.switch_button)
        self.switch_button.setNavigation(self.signout_button, self.cancel_button,
                                         self.cancel_button, self.signout_button)
        self.signout_button.setNavigation(self.cancel_button, self.switch_button,
                                          self.switch_button, self.cancel_button)


def manage_plex(context):
    try:
        with PlexManage(i18n('Manage myPlex'), window=xbmcgui.Window(10000)) as dialog:
            dialog.set_context(context)
            dialog.start()
    except AlreadyActiveException:
        pass
    except AttributeError:
        LOG.debug('Failed to load PlexManage ...')


def _manual_signin(context):
    """Prompt for myPlex username/password via the skin keyboard and sign in.

    Returns True on success, False otherwise.
    """
    username = DIALOG.input(i18n('Username:'))
    if not username:
        return False

    password = DIALOG.input(i18n('Password:'), option=xbmcgui.ALPHANUM_HIDE_INPUT)

    token = context.plex_network.sign_into_myplex(username, password)
    return token is not None and token is not False


def _check_pin(context, identifier):
    """Poll plex.tv to see whether the displayed PIN has been linked yet."""
    try:
        return bool(context.plex_network.check_signin_status(identifier))
    except Exception:  # pylint: disable=broad-except
        LOG.debug('PIN sign in check failed ...')
        return False


def sign_in_to_plex(context, refresh=True):
    """Sign into myPlex using the skin's native dialog.

    Presents the PIN link flow with three buttons: Cancel, Manual and Done.
    """
    xbmc.executebuiltin('Dialog.Close(all,true)')

    window = xbmcgui.Window(10000)
    active_property = '-'.join([CONFIG['id'], 'dialog_active'])
    if window.getProperty(active_property) == 'true':
        return False
    window.setProperty(active_property, 'true')

    status = False
    try:
        error = False
        while True:
            response = context.plex_network.get_signin_pin()
            identifier = response.get('id', '')
            code = ' '.join(response.get('code', []))

            message = i18n('From your computer, go to %s and enter the code below') % \
                '[B]https://www.plex.tv/link/[/B]'
            message += '[CR][CR][B]%s[/B]' % code
            if error:
                message += '[CR][CR][COLOR red]%s[/COLOR]' % i18n('Unable to sign in')

            # nolabel -> Cancel (0), customlabel -> Manual (2), yeslabel -> Done (1)
            choice = DIALOG.yesnocustom(i18n('myPlex Login'), message,
                                        i18n('Manual'), i18n('Cancel'), i18n('Done'))

            if choice == 1:  # Done -> the user linked the PIN, verify it
                if _check_pin(context, identifier):
                    status = True
                    break
                error = True
                continue

            if choice == 2:  # Manual -> username/password entry
                if _manual_signin(context):
                    status = True
                    break
                error = True
                continue

            # Cancel (0) or dialog dismissed (-1)
            break

        status = status or context.plex_network.is_myplex_signedin()

        if status:
            LOG.debug('Sign in successful ...')
            DIALOG.notification(i18n('myPlex Login'), i18n('Successfully signed in'),
                                xbmcgui.NOTIFICATION_INFO)
        else:
            LOG.debug('Sign in cancelled or failed ...')
    finally:
        window.clearProperty(active_property)

    if refresh:
        xbmc.executebuiltin('Container.Refresh')

    return status


def sign_out(context, refresh=True):
    can_signout = True
    if not context.plex_network.is_admin():
        can_signout = False
        _ = DIALOG.ok(i18n('Sign Out'),
                      i18n('To sign out you must be logged in as an admin user. '
                           'Switch user and try again'))
    if can_signout:
        result = DIALOG.yesno(i18n('myPlex'),
                              i18n('You are currently signed into myPlex.'
                                   ' Are you sure you want to sign out?'))
        if result:
            context.plex_network.signout()
            if refresh:
                xbmc.executebuiltin('Container.Refresh')


def switch_user(context, refresh=True):
    user_list = context.plex_network.get_plex_home_users()
    # zero means we are not plexHome'd up
    if user_list is None or len(user_list) == 1:
        LOG.debug('No users listed or only one user, Plex Home not enabled')
        return False

    LOG.debug('found %s users: %s' % (len(user_list), user_list.keys()))

    # Get rid of currently logged in user.
    user_list.pop(context.plex_network.get_myplex_user(), None)

    user_names = list(user_list.keys())
    result = DIALOG.select(i18n('Switch User'), user_names)
    if result == -1:
        LOG.debug('Dialog cancelled')
        return False

    LOG.debug('user [%s] selected' % user_names[result])
    user = user_list[user_names[result]]

    pin = None
    if user['protected'] == '1':
        LOG.debug('Protected user [%s], requesting password' % user['title'])
        pin = DIALOG.input(i18n('Enter PIN'), type=xbmcgui.INPUT_NUMERIC,
                           option=xbmcgui.ALPHANUM_HIDE_INPUT)

    success, message = context.plex_network.switch_plex_home_user(user['id'], pin)

    if not success:
        DIALOG.ok(i18n('Switch Failed'), message)
        LOG.debug('Switch User Failed')
        return False

    if refresh:
        xbmc.executebuiltin('Container.Refresh')

    return True

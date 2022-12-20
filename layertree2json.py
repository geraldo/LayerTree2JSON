# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LayerTree2JSON
                                 A QGIS plugin
 Parse QGIS 3 project files and write a JSON config file with layer information.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2022-07-05
        git sha              : $Format:%H$
        copyright            : (C) 2022 by Gerald Kogler/PSIG
        email                : geraldo@servus.at
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QFileInfo, QUrl
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.core import QgsProject, Qgis, QgsLayerTreeLayer, QgsLayerTreeGroup, QgsVectorLayer, QgsAttributeEditorElement, QgsExpressionContextUtils, QgsProviderRegistry
from qgis.gui import QgsGui
import json
import unicodedata
import webbrowser
import pysftp
import urllib.parse
from datetime import datetime

from .resources import *
from .layertree2json_dialog import LayerTree2JSONDialog
from .layertree2json_dialog_settings import LayerTree2JSONDialogSettings, settings
import os.path
from tempfile import gettempdir


class LayerTree2JSON:

    def __init__(self, iface):
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'LayerTree2JSON_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&LayerTree2JSON')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('LayerTree2JSON', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToWebMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        self.add_action(
            os.path.join(os.path.dirname(__file__), "icon.png"),
            text=self.tr(u'Parse Layers and save JSON'),
            callback=self.run,
            parent=self.iface.mainWindow())
        self.add_action(
            os.path.join(os.path.dirname(__file__), "help.svg"),
            text=self.tr(u'Help'),
            callback=self.help,
            parent=self.iface.mainWindow(),
            add_to_toolbar=False)

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginWebMenu(
                self.tr(u'&LayerTree2JSON'),
                action)
            self.iface.removeToolBarIcon(action)


    def show_online_file(self):
        # add timestamp to path to avoid cache
        webbrowser.open(self.projectHost + '/' + self.projectJsonPath2 + self.projectQgsFile + '.json?' + str(datetime.timestamp(datetime.now())))


    def show_project(self):
        path = self.projectName
        # exception for project ctbb which has different sub projects
        if path == 'ctbb':
            path += '/index'
            if self.projectFilename != 'poum':
                path += '_' + self.projectFilename.replace('.qgs', '')
            path += '.php'
        webbrowser.open(self.projectHost + '/' + path)


    def radioStateLocal(self, state):
        if state.isChecked() == True:
            self.dlg.radioProject.setEnabled(False)


    def radioStateUpload(self, state):
        if state.isChecked() == True:
            self.dlg.radioProject.setEnabled(True)


    def inputsFtpOk(self, host=None, user=None, password=None):
        host = host or self.projectHost
        user = user or self.projectUser
        password = password or self.projectPassword

        if host == "" or user == "" or password == "":

            self.iface.messageBar().pushMessage(
                "Warning", "You have to define Host, User and Password in Project Settings in order to use FTP",
                level=Qgis.Warning, duration=3)
            return False
        else: 
            return True


    def connectToFtp(self, uploadFile=False, uploadPath=False, host=None, user=None, password=None):
        host = host or self.projectHost
        user = user or self.projectUser
        password = password or self.projectPassword

        try:
            cnopts = pysftp.CnOpts()
            cnopts.hostkeys = None
            sftp = pysftp.Connection(host=host, 
                username=user, 
                password=password, 
                cnopts=cnopts)

            if uploadFile and uploadPath:
                if not sftp.exists(uploadPath):
                    sftp.makedirs(uploadPath)
                    sftp.chmod(uploadPath, mode=777)

                sftp.chdir(uploadPath)
                sftp.put(uploadFile)

                #self.iface.messageBar().pushMessage("Success", "File UPLOADED to host " + host, level=Qgis.Success, duration=3)
            else:
                self.iface.messageBar().pushMessage("Success", "FTP connection ESTABLISHED to host " + host, level=Qgis.Success, duration=3)

            sftp.close()
        except:
            self.iface.messageBar().pushMessage("Warning", "FTP connection FAILED to host " + host, level=Qgis.Warning, duration=3)
 

    def replaceSpecialChar(self, text):
        chars = "!\"#$%&'()*+,./:;<=>?@[\\]^`{|}~¬·"
        for c in chars:
            text = text.replace(c, "")
        return text


    def stripAccents(self, str):
       return ''.join(c for c in unicodedata.normalize('NFD', str)
                      if unicodedata.category(c) != 'Mn')


    def getDataProvider(self, layerId, type):
        # https://gis.stackexchange.com/a/447119/60146
        layer = QgsProject.instance().mapLayer(layerId)
        uri_components = QgsProviderRegistry.instance().decodeUri(layer.dataProvider().name(), layer.publicSource());

        if type and type in uri_components:
            return uri_components[type]
        else:
            return None


    # code based on https://github.com/geraldo/qgs-layer-parser
    def getLayerTree(self, node, project_file):
        obj = {}

        if isinstance(node, QgsLayerTreeLayer):
            obj['name'] = node.name()
            obj['id'] = node.layerId()
            obj['provider'] = node.layer().providerType()
            obj['visible'] = node.isVisible()
            obj['hidden'] = node.name().startswith("@") # hide layer from layertree
            if obj['hidden']:
                obj['visible'] = True   # hidden layers/groups have to be visible by default
            obj['showlegend'] = not node.name().startswith("~") and not node.name().startswith("¬") # don't show legend in layertree

            # WFS vector layers
            vectorial = False
            # print("Vector layers:", QgsProject.instance().readListEntry("WFSLayers", "/")[0]);
            if node.layerId() in QgsProject.instance().readListEntry("WFSLayers", "/")[0]:
                vectorial = True
            obj['vectorial'] = vectorial

            # base layer
            if str(node.layer().type()) == 'QgsMapLayerType.RasterLayer' and node.layer().providerType() == 'wms':

                obj['type'] = "baselayer"
                obj['url'] = self.getDataProvider(node.layerId(), 'url')

            else:

                obj['type'] = "layer"
                obj['path'] = self.getDataProvider(node.layerId(), 'path')
                obj['qgisname'] = node.name()   # internal qgis layer name with all special characters
                obj['indentifiable'] = node.layerId() not in QgsProject.instance().nonIdentifiableLayers()
                obj['fields'] = []
                obj['actions'] = []
                obj['external'] = node.name().startswith("¬")

                layer_package_name = QgsExpressionContextUtils.layerScope(node.layer()).variable("layer_package_name")
                if layer_package_name:
                    obj['package_name'] = layer_package_name
                layer_package_format = QgsExpressionContextUtils.layerScope(node.layer()).variable("layer_package_format")
                if layer_package_format:
                    obj['package_format'] = layer_package_format

                if hasattr(self, 'projectTilecache'):
                    if self.projectTilecache:
                        obj['mapproxy'] = project_file + "_layer_" + self.replaceSpecialChar(self.stripAccents(obj['name'].lower().replace(' ', '_')))

                # remove first character
                if not obj['showlegend']:
                    obj['name'] = node.name()[1:]

                # fetch layer directly from external server (not from QGIS nor mapproxy)
                if obj['external']:
                    obj['name'] = node.name()[1:]
                    src = QgsProject.instance().mapLayer(node.layerId()).source()
                    
                    # wms url
                    istart = src.index("url=")+4
                    try:
                        iend = src.index("&", istart)
                    except ValueError:
                        iend = len(src)
                    obj['wmsUrl'] = src[istart:iend]
                    
                    # wms layers
                    istart = src.index("layers=")+7
                    try:
                        iend = src.index("&", istart)
                    except ValueError:
                        iend = len(src)
                    obj['wmsLayers'] = src[istart:iend]
                    
                    # wms srs
                    istart = src.index("crs=")+4
                    try:
                        iend = src.index("&", istart)
                    except ValueError:
                        iend = len(src)
                    obj['wmsProjection'] = src[istart:iend]

                #print("- layer: ", node.name())

                layer = QgsProject.instance().mapLayer(node.layerId())

                # write SLD for WFS vector layers
                if vectorial:
                    sldFile = self.projectFolder + os.path.sep + node.name() + ".sld"
                    # print("write sld to:", sldFile)
                    layer.saveSldStyle(sldFile)
                    if (self.dlg.radioUpload.isChecked() or self.dlg.radioUploadFiles.isChecked()) and self.inputsFtpOk():
                        # upload SLD file to server by FTP
                        self.connectToFtp(sldFile, self.projectJsonPath + self.projectJsonPath2)


                if obj['indentifiable'] and isinstance(layer, QgsVectorLayer):

                    fields = []

                    # get all fields like arranged using the Drag and drop designer
                    edit_form_config = layer.editFormConfig()
                    root_container = edit_form_config.invisibleRootContainer()
                    for field_editor in root_container.findElements(QgsAttributeEditorElement.AeTypeField):
                        i = field_editor.idx()
                        if i >= 0 and layer.editorWidgetSetup(i).type() != 'Hidden':
                            #print(i, field_editor.name(), layer.fields()[i].name(), layer.attributeDisplayName(i))

                            f = {}
                            f['name'] = layer.attributeDisplayName(i)
                            obj['fields'].append(f)

                    for action in QgsGui.instance().mapLayerActionRegistry().mapLayerActions(layer):
                        a = {}
                        a['name'] = action.name()
                        a['action'] = action.action()
                        obj['actions'].append(a)

            return obj

        elif isinstance(node, QgsLayerTreeGroup):
            obj['name'] = node.name()
            obj['qgisname'] = node.name()   # internal qgis layer name with all special characters
            obj['type'] = "group"
            obj['visible'] = node.isVisible()
            obj['hidden'] = node.name().startswith("@")
            if obj['hidden']:
                obj['visible'] = True   # hidden layers/groups have to be visible by default
            obj['showlegend'] = not node.name().startswith("~") # don't show legend in layertree
            obj['children'] = []
            obj['vectorial'] = False # groups can't be vectorial for now
            #print("- group: ", node.name())
            #print(node.children())

            if hasattr(self, 'projectTilecache'):
                if self.projectTilecache:
                    obj['mapproxy'] = project_file + "_group_" + self.replaceSpecialChar(self.stripAccents(obj['name'].lower().replace(' ', '_')))

            # remove first character
            if not obj['showlegend']:
                obj['name'] = node.name()[1:]

            for child in node.children():
                if not child.name().startswith("¡"):
                    obj['children'].append(self.getLayerTree(child, project_file))

        return obj


    # find static layer files and upload them using FTP
    def uploadFilesLayerTree(self, node):
        if isinstance(node, QgsLayerTreeLayer):
            path = self.getDataProvider(node.layerId(), 'path')

            # get used static layer files
            if path and os.path.isfile(path):
                uriPath = path.replace(self.projectFolder + os.path.sep, "")
                uriPathList = uriPath.split(os.path.sep)
                uriFile = uriPathList[len(uriPathList)-1]

                if os.path.sep in uriPath:
                    # file in subfolder
                    uriFolder = uriPath.replace(uriFile, "").strip()
                    remotePath = self.projectQgsPath + uriFolder
                else:
                    remotePath = self.projectQgsPath

                self.connectToFtp(path, remotePath)
                self.iface.messageBar().pushMessage("Success", "Used layer file " + uriFile + " published at " + remotePath, level=Qgis.Success, duration=3)

        elif isinstance(node, QgsLayerTreeGroup):
            for child in node.children():
                if not child.name().startswith("¡"):
                    self.uploadFilesLayerTree(child)


    def update_project_vars(self, init=False):

        #print("update_project_vars", settings.activeProject, self.dlg.inputProjects.currentIndex())
        if settings.activeProject != -1 and self.dlg.inputProjects.currentIndex() >= 0:

            project = settings.userProjects[self.dlg.inputProjects.currentIndex()]
            self.projectName = project[0]
            self.projectQgsFile = project[1]
            self.projectQgsPath = project[2]
            self.projectJsonPath = project[3]
            self.projectJsonPath2 = project[4]
            self.projectHost = project[5]
            self.projectUser = project[6]
            self.projectPassword = project[7]
            # compability to migrate to plugin v0.3.1
            if len(project) > 8:
                self.projectTilecache = project[8]
            else:
                self.projectTilecache = True

            self.dlg.radioUpload.setEnabled(True)
            self.dlg.radioUploadFiles.setEnabled(True)

            if init:
                settings.activeProject = self.dlg.inputProjects.currentIndex()
                QSettings().setValue('/LayerTree2JSON/ActiveProject', settings.activeProject)
                #print("change active project to", settings.activeProject)


    """settings dialog"""
    def settings(self):
        '''Show the settings dialog box'''
        self.settingsDlg.show()

    def help(self):
        '''Display a help page'''
        url = QUrl.fromLocalFile(os.path.dirname(__file__) + "/docs/index.html").toString()
        webbrowser.open(url, new=2)

    def addProject(self):
        self.settingsDlg.inputProjectName.clear()
        self.settingsDlg.inputQgsFile.clear()
        self.settingsDlg.inputQgsPath.clear()
        self.settingsDlg.inputJsonPath.clear()
        self.settingsDlg.inputJsonPath2.clear()
        self.settingsDlg.inputHost.clear()
        self.settingsDlg.inputUser.clear()
        self.settingsDlg.inputPassword.clear()
        self.settingsDlg.radioMapproxy.setChecked(True)
        self.settingsDlg.isNew = True
        self.settingsDlg.show()

    def editProject(self):
        if self.dlg.inputProjects.count() > 0:
            index = self.dlg.inputProjects.currentIndex()
            if index >= 0:
                userProject = settings.userProjects[index]
                self.settingsDlg.inputProjectName.setText(userProject[0])
                self.settingsDlg.inputQgsFile.setText(userProject[1])
                self.settingsDlg.inputQgsPath.setText(userProject[2])
                self.settingsDlg.inputJsonPath.setText(userProject[3])
                self.settingsDlg.inputJsonPath2.setText(userProject[4])
                self.settingsDlg.inputHost.setText(userProject[5])
                self.settingsDlg.inputUser.setText(userProject[6])
                self.settingsDlg.inputPassword.setText(userProject[7])

                # compability to migrate to plugin v0.3.1
                self.settingsDlg.radioMapproxy.setChecked(True)
                if len(userProject) > 8 and not userProject[8]:
                    self.settingsDlg.radioQgisserver.setChecked(True)

                self.settingsDlg.isNew = False
                self.settingsDlg.show()

    def removeProject(self):
        if self.dlg.inputProjects.count() > 0:
            index = self.dlg.inputProjects.currentIndex()
            if index >= 0:
                del settings.userProjects[index]
                if settings.userProjects:
                    QSettings().setValue('/LayerTree2JSON/UserProjects', settings.userProjects)
                else:
                    QSettings().setValue('/LayerTree2JSON/UserProjects', 0)
                
                if self.dlg.inputProjects.count() > 0:
                    QSettings().setValue('/LayerTree2JSON/ActiveProject', 0)

                names = []
                for item in settings.userProjects:
                    names.append(item[0])
                self.dlg.inputProjects.clear()
                self.dlg.inputProjects.addItems(names)

                if len(names) == 0:
                    self.dlg.buttonEditProject.setEnabled(False);
                    self.dlg.buttonRemoveProject.setEnabled(False);
                    self.dlg.radioUpload.setEnabled(False)
                    self.dlg.radioUploadFiles.setEnabled(False)


    """Run method that performs all the real work"""
    def run(self):

        if (QgsProject.instance().fileName() == ""):
            self.iface.messageBar().pushMessage(
                  "Warning", "Please open a project file in order to use this plugin",
                  level=Qgis.Warning, duration=3)

        else:
            # define global variables
            self.projectFilename = QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable("project_filename")
            self.projectFolder = QgsExpressionContextUtils.projectScope(QgsProject.instance()).variable("project_folder")

            # Create the dialog with elements (after translation) and keep reference
            if self.first_start:
                self.first_start = False
                self.dlg = LayerTree2JSONDialog()
                self.settingsDlg = LayerTree2JSONDialogSettings(self, self.iface, self.iface.mainWindow())

                # set Project list
                names = []
                for item in settings.userProjects:
                    names.append(item[0])
                self.dlg.inputProjects.clear()
                self.dlg.inputProjects.addItems(names)

                if type(settings.activeProject) == int and int(settings.activeProject) >= 0:
                    self.dlg.inputProjects.setCurrentIndex(settings.activeProject)
                    self.update_project_vars(True)

                self.dlg.buttonEditProject.setEnabled(len(names) > 0);
                self.dlg.buttonRemoveProject.setEnabled(len(names) > 0);

                # connect GUI                
                self.dlg.radioLocal.toggled.connect(lambda:self.radioStateLocal(self.dlg.radioLocal))
                self.dlg.radioUpload.toggled.connect(lambda:self.radioStateUpload(self.dlg.radioUpload))
                self.dlg.radioUploadFiles.toggled.connect(lambda:self.radioStateUpload(self.dlg.radioUploadFiles))
                self.dlg.inputProjects.currentIndexChanged.connect(self.update_project_vars)

                self.dlg.buttonNewProject.clicked.connect(self.addProject)
                self.dlg.buttonEditProject.clicked.connect(self.editProject)
                self.dlg.buttonRemoveProject.clicked.connect(self.removeProject)
                self.dlg.buttonBox.helpRequested.connect(self.help)

            # show the dialog
            self.dlg.show()
            result = self.dlg.exec_()

            # See if OK was pressed
            if result:

                # check if active project file has same name then selected project
                if self.projectName != self.projectFilename.split(".")[0]:
                    self.iface.messageBar().pushMessage("Warning", "Your active project file name '" + self.projectFilename.split(".")[0] + "' differs from selected project '" + self.projectName + "'. Please check!", level=Qgis.Warning, duration=3)

                # check mode
                elif ((self.dlg.radioUpload.isChecked() or self.dlg.radioUploadFiles.isChecked()) and self.inputsFtpOk()) or self.dlg.radioLocal.isChecked():

                    # prepare file names
                    project_file = self.projectFilename.replace('.qgs', '')
                    # exception for project ctbb
                    if 'projectName' in locals() and self.projectName == 'ctbb':
                        project_file = 'ctbb_' + project_file

                    # parse QGS file to JSON
                    info=[]
                    for group in QgsProject.instance().layerTreeRoot().children():
                        if not group.name().startswith("¡"):
                            info.append(self.getLayerTree(group, project_file))

                    # write JSON to temporary file and show in browser
                    filenameJSON = self.projectFolder + os.path.sep + self.projectFilename + '.json'
                    file = open(filenameJSON, 'w')
                    file.write(json.dumps(info))
                    file.close()

                    if (self.dlg.radioUpload.isChecked() or self.dlg.radioUploadFiles.isChecked()) and self.inputsFtpOk():
                        # upload JSON file to server by FTP
                        self.connectToFtp(filenameJSON, self.projectJsonPath + self.projectJsonPath2)
                        # public URL of JSON file
                        filenameJSON = self.projectHost + '/' + self.projectJsonPath2 + self.projectFilename + '.json'
                        
                        # upload QGS file to server by FTP
                        self.connectToFtp(self.projectFolder + os.path.sep + self.projectFilename, self.projectQgsPath)
                        self.iface.messageBar().pushMessage(
                          "Success", "QGS file " + self.projectFilename + " published at " + self.projectQgsPath, level=Qgis.Success, duration=3)

                        if self.dlg.radioUploadFiles.isChecked():
                            # iterate over layer tree and check if static layer files used
                            for group in QgsProject.instance().layerTreeRoot().children():
                                if not group.name().startswith("¡"):
                                    self.uploadFilesLayerTree(group)
                    
                    if self.dlg.radioProject.isChecked():
                        self.show_project()
                    elif self.dlg.radioJson.isChecked():
                        if self.dlg.radioUpload.isChecked() or self.dlg.radioUploadFiles.isChecked():
                            self.show_online_file()
                        else:
                            webbrowser.open(filenameJSON)

                    # message to user
                    self.iface.messageBar().pushMessage("Success", "JSON file published at " + filenameJSON, level=Qgis.Success, duration=3)

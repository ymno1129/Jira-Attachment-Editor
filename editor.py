from jira import JIRA
from PySide import QtGui, QtCore, QtUiTools, QtXml
from PIL import Image
from time import gmtime, strftime
import os
import json
import sys
import warnings

#Suppress all warning messages cuz they are annoying
warnings.filterwarnings("ignore")

class Date():
    def __init__(self, date):
        self.date_str = date
        self.year = date[:4]
        self.month = date[5:7]
        self.day = date[8:10]
        self.hour = date[11:13]
        self.minute = date[14:16]
        self.second = date[17:19]
        self.time_components = [self.year, self.month, self.day, self.hour, self.minute, self.second]

    def getDateSimplified(self):
        return self.date_str[:self.date_str.find('.')]
        
    def getDateFormatted(self, format):
        #TODO
        pass
    
    def getTimeComponents(self):
        return self.time_components
        
    def __gt__(self, other):
        result = False
        other_time_components = other.getTimeComponents()
        for idx, component in enumerate(self.time_components):
            other_component = other_time_components[idx]
            if int(component) > int(other_component):
                result = True
                break
        return result
       
class AttachmentEditor():
    def __init__(self, needs_auth=True):
        self.default_size = (1038, 385)
        self.expanded_size = (1038, 648)
        
        self.folded = False
        self.show_log = False
        self.log_index = 1
    
        self.app = QtGui.QApplication([])
        self.login_window = QtUiTools.QUiLoader().load("ui/login.ui")
        self.main_window = QtUiTools.QUiLoader().load("ui/main.ui")
        
        self.jira = None
        self.jira_server_title = ""
        self.issue = None
        self.current_issue_id = ""
        
        if os.path.exists("profile.json"):
            with open("profile.json", 'r') as f:
                j = json.load(f)
                self.server_url = j["server"]
                self.username = j["username"]
                self.password = j["password"]
        else:
            self.server_url = ""
            self.username = ""
            self.password = ""
        
        if (needs_auth):
            self.showLoginWindow()           
        else:
            self.launchMain()
            
        self.initial_loading_complete = False
        self.attachments_mapping = {}  # {filename: (file, id, sufix)...}
        self.original_attachments = {} # copy of above
        self.selectedAttachment = ""
        
        self.changed_attachments = {}
        
        self.app.exec_()

    def showLoginWindow(self):
        self.login_window.show() 
        self.login_window.server.setText(self.server_url)
        self.login_window.username.setText(self.username)
        self.login_window.password.setText(self.password)
        self.login_window.accepted.connect(self.confirmLogin)
        
    def confirmLogin(self):
        self.server_url = self.login_window.server.text()
        self.username = self.login_window.username.text()
        self.password = self.login_window.password.text()
        
        #print self.server_url, self.username, self.password
        
        success = False
        try:
            self.jira = self.connect_to_JIRA(self.server_url, auth=(self.username, self.password))
            success = True
            self.current_user = self.jira.current_user()[:self.jira.current_user().find('%')]
        except Exception as e:
            print e
            self.displayWarning("Failed", "Login failed. Please retry.")
            
        if success:
            user_info = {"server": self.server_url, "username": self.username, "password": self.password}
            with open("profile.json", 'w') as output:
                json.dump(user_info, output)
            self.displayInfo("Success", "You have logged in successfully!")
            self.logged_in_user = ""
            self.launchMain()
            self.jira_server_title = self.jira.server_info()["serverTitle"]
        else:
            self.server_url = ""
            self.username = ""
            self.password = ""
            self.showLoginWindow()
            
    def launchMain(self):
        self.main_window.show()
        self.main_window.getButton.clicked.connect(self.getIssueById)
                
        self.original_tree = self.main_window.originalTree
        self.original_tree.itemDoubleClicked.connect(self.showAttachment)
        self.original_tree.header().setClickable(True)
        self.original_tree.header().sectionClicked.connect(self.sortOriginalByColumn)
        
        self.current_tree = self.main_window.currentTree
        self.current_tree.itemDoubleClicked.connect(self.triggerEditCurrent)
        self.current_tree.itemChanged.connect(self.attachmentRenamed)
        self.current_tree.itemSelectionChanged.connect(self.attachmentSelected)
        self.current_tree.header().setClickable(True)
        self.current_tree.header().sectionClicked.connect(self.sortCurrentByColumn)
        
        self.main_window.updateButton.clicked.connect(self.updateAttachments)
        self.main_window.showLogButton.clicked.connect(self.showLogPanel)
                
    def getIssueById(self):
        msg = "Fetching data from JIRA server. Please wait..."
        self.initializeProgressBar(msg)
        id = self.main_window.issueId.text().upper()
        self.initial_loading_complete = False
        try:
            #Get issue object, its attachments and fill the data structures
            jira_issue = self.jira.issue(id)
            self.issue = jira_issue
            self.current_issue_id = id
            attachments = self.issue.fields.attachment
            num_attachments = len(attachments)
            #Reset data structures
            self.attachments_mapping = {}  
            self.original_attachments = {}
            print "reset done"
            
            for idx, attachment in enumerate(attachments):
                file_name = str(attachment)
                file_sufix = '.' + str(attachment).split('.')[1]
                file_author = attachment.author.displayName
                file_created_date = attachment.created
                self.attachments_mapping[file_name] = (attachment.get(), attachment.id, file_sufix, file_author, file_created_date)
                self.changed_attachments[file_name] = file_name
                self.refreshProgressBar(num_attachments, idx + 1)
            
            #Make a copy of the original attachments
            self.original_attachments = dict(self.attachments_mapping)
            
            #Add attachment names to display
            self.refreshDisplayPanel(self.original_tree, self.original_attachments)
            self.refreshDisplayPanel(self.current_tree, self.original_attachments, True)
           
            #print "ori = ", self.original_attachments.keys()
            #print "curr = ", self.attachments_mapping.keys()
            self.initial_loading_complete = True
            
        except Exception as e:
            warning_msg = "Issue <%s> not found! Please retry!" % str(id)
            self.displayWarning("Warning", warning_msg)
            self.main_window.issueId.setText(self.current_issue_id)
            if self.issue:
                self.initial_loading_complete = True
            
        self.progress_window.close()
      
    def showAttachment(self, item, col):
        attachment_name = item.text(0)
        attachment_sufix = self.original_attachments[attachment_name][2]
        attachment_path = "attachments/" + attachment_name + attachment_sufix if attachment_sufix not in attachment_name else "attachments/" + attachment_name
        pic_sufixes = {".png": 1, ".PNG": 1, ".bmp": 1, ".BMP": 1, ".jpg": 1, ".JPG": 1, ".jpeg": 1, ".JPEG": 1}
        try:
            with open(attachment_path, 'wb') as output:
                output.write(self.original_attachments[attachment_name][0])
            if attachment_sufix in pic_sufixes:
                image = Image.open(attachment_path)
                image.show()
            else:
                #TODO text file support 
                self.text_window = QtUiTools.QUiLoader().load("ui/textPanel.ui")
                with open(attachment_path, 'r') as input:
                    content = input.read()
                    self.text_window.textDisplay.document().setPlainText(content)
                    self.text_window.show()

        except Exception as e:
            raise
            print "ERROR ", e
        
        print attachment_path
    
    def triggerEditCurrent(self, item, col):
        if col != 0:
            return
        try:
            self.current_tree.editItem(item, col)
        except Exception as e:
            raise
    
    def attachmentSelected(self):
        if self.current_tree.currentItem():
            self.selectedAttachment = self.current_tree.currentItem().text(0)
        
    def attachmentRenamed(self, item, col):
        #print "called", self.initial_loading_complete, self.selectedAttachment
        if self.initial_loading_complete and self.selectedAttachment != "":
            new_name = item.text(0)
            hit = False
            for original_name in self.changed_attachments:
                if self.selectedAttachment == original_name:
                    self.changed_attachments[original_name] = new_name
                    #print "1st changing for %s" % (original_name)
                    hit = True
                    break
            if not hit:
                for original_name in self.changed_attachments:
                    if self.selectedAttachment == self.changed_attachments[original_name]:
                        self.changed_attachments[original_name] = new_name
                        #print "2nd changing for %s" % (original_name)
                        break
           
            self.attachments_mapping[new_name] = self.attachments_mapping.pop(self.selectedAttachment)
            self.selectedAttachment = new_name
            
    def updateAttachments(self):
        num_attachments_to_be_updated = 0
        attachments_to_be_deleted = {}
        for attachment in self.original_attachments:
            final_name = self.changed_attachments[attachment]
            sufix = self.original_attachments[attachment][2]
            if final_name == attachment or final_name + sufix == attachment:
                continue
            num_attachments_to_be_updated += 1
            attachments_to_be_deleted[attachment] = final_name
        
        self.generateLog(attachments_to_be_deleted)
        
        if len(attachments_to_be_deleted) == 0:
            return
        
        msg = "Deleting modified attachments!"
        self.initializeProgressBar(msg)
        index = 0
        #Delete all changed
        for attachment in attachments_to_be_deleted:
            id = self.original_attachments[attachment][1]
            self.jira.delete_attachment(id)
            index += 1
            self.refreshProgressBar(num_attachments_to_be_updated, index)
            
        #Re-upload all changed
        success = False
        msg = "Updating modified attachments!"
        self.initializeProgressBar(msg)
        num_attachments = len(self.changed_attachments)
        index = 0
        for attachment in attachments_to_be_deleted:
            new_name = attachments_to_be_deleted[attachment]
            attachment_info = self.attachments_mapping[new_name]
            f = attachment_info[0]
            sufix = attachment_info[2]
            file_name = new_name + sufix if sufix not in new_name else new_name
            
            #Create a local temp copy to upload
            with open(file_name, 'wb') as tmp_out:
                tmp_out.write(f)
            with open(file_name, 'rb') as to_upload:
                try:
                    self.jira.add_attachment(issue=self.issue, attachment=to_upload, filename=file_name) 
                    success = True
                    index += 1
                    self.refreshProgressBar(num_attachments, index)
                except Exception as e:
                    print e
                    
            #Delete local copy
            os.remove(file_name)
            
        if success:
            self.displayInfo("Success", "Attachments have been renamed successfully.")
            self.selectedAttachment = ""
            self.changed_attachments = {}
            self.getIssueById()
            #print "ori after = ", self.original_attachments.keys()
            #print "curr after = ", self.attachments_mapping.keys()
            a = 1
   
    #Using python JIRA module
    def connect_to_JIRA(self, server_url, auth):
        options = {'server': server_url, 'verify':False}
        jiraInstance = JIRA(options, basic_auth = auth, max_retries=0)
        return jiraInstance

    def showLogPanel(self):
        if self.show_log:
            self.main_window.setFixedSize(self.default_size[0], self.default_size [1])
            self.main_window.showLogButton.setText("SHOW LOG")
            self.show_log = False
        else:
            self.main_window.setFixedSize(self.expanded_size[0], self.expanded_size [1])
            self.main_window.showLogButton.setText("HIDE LOG")
            self.show_log = True
 
    def refreshDisplayPanel(self, panel, content, editable=False, sort_key=None):
        while (panel.topLevelItemCount() > 0):
            panel.takeTopLevelItem(0)
            
        sorted_data = []
        for file_name in content:
            sorted_data.append((file_name, content[file_name]))
            
        if sort_key:
            sorting_method = None
            if sort_key == "Name":
                sorting_method = lambda x: x[0]
            elif sort_key == "Author":
                sorting_method = lambda x: x[1][3].split(' ')[0]
            elif sort_key == "Date":
                sorting_method = lambda x: x[1][4]
            sorted_data = (sorted(sorted_data, key=sorting_method))[::-1]
            
        #print sorted_data
        for data in sorted_data:
            file_name = data[0]
            author = data[1][3]
            date = Date(data[1][4])
            date = date.getDateSimplified()
            item = QtGui.QTreeWidgetItem()
            item.setText(0, file_name)
            item.setText(1, author)
            item.setText(2, date)
            panel.insertTopLevelItem(0, item)
        
        if editable:
            for x in xrange(0, panel.topLevelItemCount()):
                item = panel.topLevelItem(x)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
    
    def sortOriginalByColumn(self, col):
        key_map = {0: "Name", 1: "Author", 2: "Date"}
        key = key_map[col]
        self.refreshDisplayPanel(self.original_tree, self.original_attachments, sort_key=key)
    
    def sortCurrentByColumn(self, col):
        key_map = {0: "Name", 1: "Author", 2: "Date"}
        key = key_map[col]
        self.refreshDisplayPanel(self.current_tree, self.attachments_mapping, editable=True, sort_key=key)
    
    def parseJiraTime(self, time):
        pass
    
    def initializeProgressBar(self, msg):
        self.progress_window = QtUiTools.QUiLoader().load("ui/progress.ui")
        self.progress_window.progressBar.setRange(0, 100)
        self.progress_window.progressBar.setValue(1)
        self.progress_window.messageLabel.setText(msg)
        self.progress_window.show()
    
    def refreshProgressBar(self, total, current):
        if self.progress_window:
            self.progress_window.progressBar.setRange(0, total)
            self.progress_window.progressBar.setValue(current)
    
    def displayWarning(self, title, msg):
        QtGui.QMessageBox.warning(self.main_window, title, msg)
    
    def displayInfo(self, title, msg):
        QtGui.QMessageBox.information(self.main_window, title, msg)
    
    def generateLog(self, changed_attachments):
        current = self.main_window.logPanel.toPlainText()
        log = current
        for original_name in changed_attachments:
            # idx / original uploader / new uploader/ original name / new name
            log += "%d | %s | %s | %s | %s | %s | %s\n" % (self.log_index, self.original_attachments[original_name][3], self.current_user, original_name, changed_attachments[original_name], self.jira_server_title, self.current_issue_id)
            self.log_index += 1
        self.main_window.logPanel.document().setPlainText(log)
    
def testStuff():
    options = {'server': "https://hdc-tomcat-jira194.ubisoft.org/jira", 'verify':False}
    jira = JIRA(options, basic_auth = ("hui-cheng.zhuang@ubisoft.com","32194567ZHc"))
    issue = jira.issue("TES-3")
    attachments = issue.fields.attachment
    for attachment in attachments:
        name = str(attachment)
        #print attachment.__dict__.keys()
        #print attachment.author.__dict__.keys()
        print attachment.created, attachment.author.raw
        break
    sys.exit(0)  
    a = 1

def main():
    editor = AttachmentEditor()
    
if __name__ == "__main__":
    #testStuff()
    main()















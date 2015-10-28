#coding: utf-8
import types, time
import csv, cStringIO, codecs
import xml.dom.minidom
import httplib
import urllib
import sys
import optparse
import os
import simplejson
import logging
from pprint import pprint
from launchpadlib.launchpad import Launchpad
import dateutil.parser
#import pdb

CONST_TEAM = "trafodion"


def no_credential():
    print "Can't proceed without Launchpad credential."
    sys.exit()


def cleanID(id):
    # If this is a URL, return the leaf element
    lastSlash = id.rfind("/")
    if lastSlash == -1:
        return id
    else:
        lastSlash = lastSlash+1
        temp = str(id[lastSlash:])
        # If it now starts with ~, lose that
        if temp[0] == '~':
            temp = temp[1:]
        return temp


class Blueprint:
    createCsv = False
    LOG_FILENAME = 'logging_launchpad_bp.out' 

    logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG)

    if createCsv:    
        row1written = False

    def __init__(self):
        #pdb.set_trace()
        #lp = Launchpad.login_anonymously('LaunchpadBugs.py', 'production', version="devel")
        lp = Launchpad.login_with('LaunchpadBugs.py','production', version="devel", credential_save_failed=no_credential)


        # launchpad json
        lpJson = Launchpad.login_with('lplib.cookbook.json_fetcher', 'production', '.lplib-json_fetcher-cache',credential_save_failed=no_credential)
        # authenticated browser object
        jBrowser = lpJson._browser

        proj = lp.projects[CONST_TEAM]
        print proj.display_name

        all_spec_collection = proj.all_specifications_collection_link
        jResult = jBrowser.get(all_spec_collection)
        jResult = simplejson.loads(jResult)

        # for debugging only

        #with open('bp-short.json') as data_file:
        #    jResult = simplejson.load(data_file)

        # for debugging only

        print "Number of blueprints: " + str(jResult["total_size"])

        for entry in jResult["entries"]:
            bpName = entry["name"].strip()
            print ""
            print "Blueprint name : " + bpName

            if entry["lifecycle_status"] == "Complete":
                bpLastUpdated = str(entry["date_completed"]).replace('T', ' ')
                bpAssignedId = cleanID(entry["completer_link"])
            elif entry["lifecycle_status"] == "Started":
                bpLastUpdated = str(entry["date_started"]).replace('T', ' ')
                bpAssignedId = cleanID(entry["starter_link"])
            else:
                bpLastUpdated = str(entry["date_created"]).replace('T', ' ')
                bpAssignedId = None

            print "Last updated : " + bpLastUpdated

            # check if bug has been downloaded earlier
            xmlBP = LPXmlDoc(bpName, "bp")

            if xmlBP.doesXmlFileExist(bpName, bpLastUpdated) == False:
                # get BP owner
                bpOwnerID = cleanID(entry["owner_link"])
                bpOwner = lp.people(bpOwnerID)
                bpOwner = bpOwner.display_name

                # get BP assignee
                if bpAssignedId is None:
                    bpAssignedTo = ""
                else:
                    bpAssignedTo = lp.people(bpAssignedId)
                    bpAssignedTo = bpAssignedTo.display_name

                # get BP milestone
                if type(entry["milestone_link"]) is not types.NoneType:
                    bpMilestoneLink = entry["milestone_link"]

                    bpResult = jBrowser.get(bpMilestoneLink)
                    bpResult = simplejson.loads(bpResult)
                    bpMilestoneTitle = bpResult["title"].strip()
                    bpMilestoneTitle = bpMilestoneTitle[11:]
                    if bpMilestoneTitle.endswith('Beta"'):
                        bpMilestoneTitle = bpMilestoneTitle[:-7]
                else:
                    bpMilestoneLink = ""
                    bpMilestoneTitle = ""

                # get BP status
                bpStatus = entry["implementation_status"]
                if bpStatus.lower() in ["unknown", "not started", "informational"]:
                    bpStatus = "Open"
                elif bpStatus.lower() in ["deferred", "needs infrastructure", "blocked"]:
                    bpStatus = "Later"
                elif bpStatus.lower() in ["started", "slow progress", "good progress", "needs code review"]:
                    bpStatus = "In Progress"
                elif bpStatus.lower() in ["beta available", "deployment"]:
                    bpStatus = "Patch Available"

                # BP importance map
                bp_importance_map = {'Essential':'Blocker', 'High':'Critical', 'Medium':'Major', 'Low':'Minor', 'Undefined':'Major'}
                bpImportance = bp_importance_map[entry["priority"]]

                # try to guess component based on BP title
                bpComponent = ""
                if bpName.startswith("infra-"):
                    bpComponent = "Build Infrastructure"
                elif bpName.startswith("cmp-"):
                    bpComponent = "sql-cmp"
                elif bpName.startswith("security-"):
                    bpComponent = "sql-security"
                elif bpName.startswith("dtm-"):
                    bpComponent = "dtm"

                # add to xmlBP
                xmlBP.addNode("date_last_updated", bpLastUpdated, "launchpad-bp")
                xmlBP.addNode("all_bp_api_link", proj.all_specifications_collection_link, "api_links")
                xmlBP.addNode("bp_api_link", entry["self_link"], "api_links")
                xmlBP.addNode("bp_web_link", entry["web_link"], "api_links")
                xmlBP.addNode("bp_owner_link", entry["owner_link"], "api_links")
                xmlBP.addNode("linked_branches_collection_link", entry["linked_branches_collection_link"], "api_links")
                xmlBP.addNode("bugs_collection_link", entry["bugs_collection_link"], "api_links")
                xmlBP.addNode("owner", bpOwner, "launchpad-bp")
                xmlBP.addNode("assignee", bpAssignedTo, "launchpad-bp")
                xmlBP.addNode("milestone_link", bpMilestoneLink, "api_links")
                # dependencies_collection_link returns junk
                xmlBP.addNode("dependencies_collection_link", entry["dependencies_collection_link"], "api_links")
                xmlBP.addNode("milestone_title", bpMilestoneTitle, "launchpad-bp")
                xmlBP.addNode("title", entry["title"], "launchpad-bp")
                xmlBP.addNode("status", bpStatus, "launchpad-bp")
                xmlBP.addNode("importance", bpImportance, "launchpad-bp")
                xmlBP.addNode("created", str(entry["date_created"]).replace('T', ' '), "launchpad-bp")
                xmlBP.addNode("component", bpComponent, "launchpad-bp")
                xmlBP.addCData("description", entry["summary"], "launchpad-bp")

                # add whiteboard entry to comments
                if type(entry["whiteboard"]) is not types.NoneType and entry["whiteboard"] != entry["summary"]:
                    xmlBP.addComment(str(entry["date_created"]).replace('T', ' '), entry["self_link"], bpOwner, "Whiteboard", entry["whiteboard"])

                # get branches
                branchResult = jBrowser.get(entry["linked_branches_collection_link"])
                branchResult = simplejson.loads(branchResult)

                for bEntry in branchResult["entries"]:
                    branchlink = bEntry["branch_link"]
                    bresult = jBrowser.get(branchlink)
                    bresult = simplejson.loads(bresult)
                    displayname = bresult["display_name"]
                    xmlBP.addBranch(displayname)

                # get linked bugs
                bugsCResult = jBrowser.get(entry["bugs_collection_link"])
                bugsCResult = simplejson.loads(bugsCResult)

                for lbEntry in bugsCResult["entries"]:
                    bugId = lbEntry["id"]
                    bugTitle = lbEntry["title"]
                    print "Linked bug : " + str(bugId)
                    xmlBP.addLinkedBugs(str(bugId), bugTitle)

                # get work items
                if type(entry["workitems_text"]) is not types.NoneType:
                    workItemsList = [s.strip().split(':') for s in entry["workitems_text"].splitlines()]
                    for i in xrange(1, len(workItemsList)):
                        wiProgress = workItemsList[i][1].strip()
                        print "Work item : " + workItemsList[i][0]
                        print "Work item progress : " + wiProgress
                        xmlBP.addWorkItems(workItemsList[i][0].strip(), wiProgress)

                xmlBP.writeToFile(bpName)

    
class Bug:
    createCsv = False
    LOG_FILENAME = 'logging_launchpad_bugs.out' 

    logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG)

    if createCsv:    
        row1written = False

    def __init__(self):
        #launchpad = Launchpad.login_anonymously('just testing', 'production')
        launchpad = Launchpad.login_with('LaunchpadBugs.py','production',credential_save_failed=no_credential)

        p = launchpad.projects[CONST_TEAM]
        print p.display_name
        bugTasks = p.searchTasks(status=["New","Incomplete","Opinion","Invalid","Won't Fix","Expired","Confirmed","Triaged","In Progress","Fix Committed","Fix Released","Incomplete (with response)","Incomplete (without response)"])
        #bugTasks = p.searchTasks(status=["New","Incomplete","Opinion","Invalid","Won't Fix","Expired","Confirmed","Triaged","In Progress","Fix Committed","Fix Released","Incomplete (with response)","Incomplete (without response)"],tags=['infrastructure'])
        #bugTasks = p.searchTasks(status=["New","Incomplete","Opinion","Invalid","Won't Fix","Expired","Confirmed","Triaged","In Progress","Fix Committed","Fix Released","Incomplete (with response)","Incomplete (without response)"],search_text="mxosrvrs hung")
        #bugTasks = p.searchTasks(search_text="mxosrvrs hung")
        #bugTasks = p.searchTasks(status=["Fix Released"],tags=["infrastructure"],search_text="CDN")
        
        print "Number of bugs: " + str(len(bugTasks))
        bugHasAttachments = 0
        maxMessages = 0

        # launchpad json
        launchpadJson = Launchpad.login_with('lplib.cookbook.json_fetcher', 'production', '.lplib-json_fetcher-cache',credential_save_failed=no_credential)
        # authenticated browser object
        browser = launchpadJson._browser

        bugTargetDisplayName = ""
        bugTargetName = ""

        for bugTask in bugTasks:         
            # Extract the bug ID from the bug link
            bugKey = cleanID(bugTask.bug_link)
            bug = launchpad.bugs[bugKey]
            bugId = bug.id
            print "Bug ID is " + str(bugId)

            bugTaskTargetDisplayName = bugTask.bug_target_display_name
            bugTaskTargetName = bugTask.bug_target_name
            
            if bugTaskTargetName != bugTargetName:
                print "Bug id: " + str(bugId)
                print "Target name: " + bugTaskTargetName
                bugTargetName = bugTaskTargetName

            # check if this has been downloaded earlier already
            bugLastUpdated = str(bug.date_last_updated).replace('T', ' ')
            xmlBug = LPXmlDoc(bugId)

            if xmlBug.doesXmlFileExist(bugId, bugLastUpdated) == False:
                xmlBug.addNode("date_last_updated", str(bugLastUpdated))
            
                ownerLink = bug.owner_link

                if type(ownerLink) is not types.NoneType :
                    try:
                        bugTaskID = cleanID(bugTask.bug_link)
                        bug = launchpad.bugs[bugTaskID]
                        ownerID = cleanID(bug.owner_link)
                        owner = launchpad.people[ownerID]
                        reportedBy = owner.display_name
                    except Exception, e:
                        logging.error("Bug with id " + str(bugId) + " caused the following error.")
                        logging.exception(e)
                        reportedBy = ""
                else :
                    reportedBy = ""
                
                if type(bugTask.assignee_link) is not types.NoneType :
                    assignedID = cleanID(bugTask.assignee_link)
                    assignedTo = launchpad.people[assignedID].display_name
                else :
                    assignedTo = ""

                if type(bugTask.milestone_link) is not types.NoneType :
                    milestone_link = bugTask.milestone_link

                    result = browser.get(milestone_link) 
                    result = simplejson.loads(result)

                    milestone_title = result["title"].strip()
                    milestone_title = milestone_title[11:]
                    if milestone_title.endswith(' "Beta"'):
                        milestone_title = milestone_title[:-7]
                else :
                    milestone_link = ""
                    milestone_title = ""

                if bug.duplicate_of_link != None :
                    duplicate_link = bug.duplicate_of_link

                    result = browser.get(duplicate_link) 
                    result = simplejson.loads(result)
                else:
                    duplicate_link = ""
                    duplicateBugId = ""

                if bug.duplicates_collection_link != None:
                    duplicates_collection_link = bug.duplicates_collection_link

                    result = browser.get(duplicates_collection_link) 
                    result = simplejson.loads(result)

                    for entry in result["entries"]:
                        xmlBug.addDuplicate(str(entry["id"]))
                else:
                    bug.duplicates_collection_link = ""

                xmlBug.addNode("bug_api_link", bugTask.bug_link, "api_links")
                xmlBug.addNode("bug_web_link", bug.web_link)
                xmlBug.addNode("bug_owner_link", bug.owner_link, "api_links")
                xmlBug.addNode("owner", reportedBy)
                xmlBug.addNode("assignee", assignedTo)
                xmlBug.addNode("milestone_link", milestone_link, "api_links")
                xmlBug.addNode("milestone_title", milestone_title)
                xmlBug.addNode("duplicate_link", duplicate_link)
                xmlBug.addNode("duplicate_bug_id", duplicateBugId)

                bugTitle = bug.title
                bugStatus = bugTask.status
                if bugTask.status.startswith("Incomplete"):
                    bugStatus = "Incomplete"
                elif bugTask.status.startswith("New"):
                    bugStatus = "Open"
                
                # Bug Importance Map
                bug_importance_map = {'Critical':'Blocker', 'High':'Critical', 'Medium':'Major', 'Low':'Minor', 'Undecided':'Major'}
                if bugTask.importance == "Wishlist":
                    bugImportance = bugTask.importance
                else:
                    bugImportance = bug_importance_map[bugTask.importance]
                    
                dateCreated = str(bugTask.date_created).replace('T', ' ')

                xmlBug.addNode("title", bugTitle)
                xmlBug.addNode("status", bugStatus)
                xmlBug.addNode("importance", bugImportance)
                xmlBug.addNode("created", dateCreated)

                if bug.tags != None :
                    print "Tags: " + ', '.join(bug.tags)
                    # component map
                    component_tags = ['sql-exe', 'sql-cmp', 'installer', 'sql-security', 'client-jdbc-t2', 
                                      'connectivity-mxosrvr', 'dtm', 'foundation', 'client-odbc-linux', 
                                      'connectivity-dcs', 'connectivity-general', 'client-jdbc-t4', 
                                      'client-odbc-windows', 'sql-cmu', 'dev-environment', 'db-utility-odb', 
                                      'sql-general', 'client-ci', 'db-utility-backup', 'connectivity-odb', 
                                      'db-utility-restore', 'documentation']
                    for tag in bug.tags:
                        if tag == "infrastructure":
                            xmlBug.addNode("component", "Build Infrastructure")
                        elif tag in component_tags:
                            xmlBug.addNode("component", tag)
                        elif tag not in component_tags:
                            xmlBug.addNode("label", tag)
                else:
                    print "Tags: None"

                xmlBug.addCData("description", bug.description)
                xmlBug.addNode("linked_branches_collection_link", bug.linked_branches_collection_link, "api_links")
                xmlBug.addNode("activity_link", bug.activity_collection_link, "api_links")

                try:
                    result = browser.get(bug.activity_collection_link) 
                    result = simplejson.loads(result)

                    for entry in result["entries"]:
                        #get person
                        personRaw = browser.get(entry["person_link"])
                        personJson = simplejson.loads(personRaw)
                    
                        person = personJson["display_name"]
                        oldvalue = ""
                        newvalue = ""
                        eMessage = ""
                        whatchanged = ""
                        datechanged = ""

                        if (entry["oldvalue"] != None):
                            oldvalue = entry["oldvalue"]

                        if (entry["newvalue"] != None):
                            newvalue = entry["newvalue"]

                        if (entry["message"] != None):
                            eMessage = entry["message"]

                        if (entry["whatchanged"] != None):
                            whatchanged = entry["whatchanged"]

                        if (entry["datechanged"] != None):
                            datechanged = str(entry["datechanged"]).replace('T', ' ')

                        xmlBug.addActivity(datechanged, oldvalue, newvalue, whatchanged, person, eMessage)

                except Exception, e:
                        logging.error("Bug with id " + str(bugId) + " caused the following error.")
                        logging.exception(e)

                # addComment(self, datecreated, selflink, person, subject, content):
                try:
                    result = browser.get(bug.messages_collection_link) 
                    result = simplejson.loads(result)

                    for entry in result["entries"]:
                        #get person
                        personRaw = browser.get(entry["owner_link"])
                        personJson = simplejson.loads(personRaw)
                    
                        person = personJson["display_name"]
                        selflink = ""
                        subject = ""
                        content = ""
                        whatchanged = ""
                        datecreated = ""

                        if (entry["self_link"] != None):
                            selflink = entry["self_link"]

                        if (entry["subject"] != None):
                            subject = entry["subject"]

                        if (entry["content"] != None):
                            content = entry["content"]

                        if (entry["date_created"] != None):
                            datecreated = str(entry["date_created"]).replace('T', ' ')

                        if (content != bug.description): #description is also stored as a comment
                            xmlBug.addComment(datecreated, selflink, person, subject, content)

                except Exception, e:
                        logging.error("Bug with id " + str(bugId) + " caused the following error when adding a comments node.")
                        logging.exception(e)

                # get branches
                try:
                    result = browser.get(bug.linked_branches_collection_link)
                    result = simplejson.loads(result)

                    for entry in result["entries"]:
                        branchlink = entry["branch_link"]
                        bresult = browser.get(branchlink)
                        bresult = simplejson.loads(bresult)
                        displayname = bresult["display_name"]
                        xmlBug.addBranch(displayname)
                except Exception, e:
                        logging.error("Bug with id " + str(bugId) + " caused the following error.")
                        logging.exception(e)

                messages = []
                
                i = 0
                                                
                if bug.message_count > 0:
                    for message in bug.messages:
                        if len(message.bug_attachments_collection_link) > 0:
                            # find the right attachment
                            for attachment in bug.attachments:
                                if (attachment.message_link == message.self_link):
                                    print "Attachment file link is ",attachment.data_link
                                    personID = cleanID(message.owner_link)
                                    xmlBug.addMessage(str(message.date_created).replace('T', ' '), launchpad.people[personID].display_name, message.content, attachment)
                                    break
                        else:
                            personID = cleanID(message.owner_link)
                            xmlBug.addMessage(str(message.date_created).replace('T', ' '), launchpad.people[personID].display_name, message.content)

                if bug.message_count > maxMessages:
                    maxMessages = bug.message_count

                xmlBug.writeToFile(bugId);

        print "Bugs with attachements: %s" % (bugHasAttachments)
        print "Max messages on one bug: %s" % (maxMessages)
    

class LPXmlDoc:
    lptype = None

    def __init__(self, id, lp_type="bug"):
        # create root
        self.lptype = lp_type
        self.xmlDoc = xml.dom.minidom.getDOMImplementation().createDocument(None,"launchpad-" + self.lptype,None)
        self.xmlDoc.documentElement.setAttribute("id", str(id)) 

    def addAttribute(self, nodeName, attribName, attribValue):
        node = self.xmlDoc.getElementsByTagName(nodeName)[0]
        node.setAttribute(attribName, attribValue)

    def addActivity(self, datechanged, oldvalue, newvalue, whatchanged, person, message):
        if self.xmlDoc.getElementsByTagName("activities").length < 1:
            activities = self.xmlDoc.createElement("activities")
            parent = self.xmlDoc.getElementsByTagName("launchpad-" + self.lptype)[0]
            parent.appendChild(activities)
        else:
            activities = self.xmlDoc.getElementsByTagName("activities")[0]

        activity = self.xmlDoc.createElement("activity")
        activity.setAttribute("datechanged", datechanged)
        nOldvalue = self.xmlDoc.createElement("oldvalue")
        txtOldvalue = self.xmlDoc.createCDATASection(oldvalue)
        nOldvalue.appendChild(txtOldvalue)
        activity.appendChild(nOldvalue)
        nNewvalue = self.xmlDoc.createElement("newvalue")
        txtNewvalue = self.xmlDoc.createCDATASection(newvalue)
        nNewvalue.appendChild(txtNewvalue)
        activity.appendChild(nNewvalue)
        nWhatchanged = self.xmlDoc.createElement("whatchanged")
        txtWhatchanged = self.xmlDoc.createTextNode(whatchanged)
        nWhatchanged.appendChild(txtWhatchanged)
        activity.appendChild(nWhatchanged)
        nPerson = self.xmlDoc.createElement("person")
        txtPerson = self.xmlDoc.createTextNode(person)
        nPerson.appendChild(txtPerson)
        activity.appendChild(nPerson)
        nMessage = self.xmlDoc.createElement("message")
        txtMessage = self.xmlDoc.createTextNode(message)
        nMessage.appendChild(txtMessage)
        activity.appendChild(nMessage)
        activities.appendChild(activity)

    def addComment(self, datecreated, selflink, person, subject, content):
        if self.xmlDoc.getElementsByTagName("comments").length < 1:
            comments = self.xmlDoc.createElement("comments")
            parent = self.xmlDoc.getElementsByTagName("launchpad-" + self.lptype)[0]
            parent.appendChild(comments)
        else:
            comments = self.xmlDoc.getElementsByTagName("comments")[0]

        comment = self.xmlDoc.createElement("comment")
        comment.setAttribute("datecreated", datecreated)
        comment.setAttribute("commentlink", selflink)
        nPerson = self.xmlDoc.createElement("person")
        txtPerson = self.xmlDoc.createTextNode(person)
        nPerson.appendChild(txtPerson)
        comment.appendChild(nPerson)
        nSubject = self.xmlDoc.createElement("subject")
        txtSubject = self.xmlDoc.createCDATASection(subject)
        nSubject.appendChild(txtSubject)
        comment.appendChild(nSubject)
        nContent = self.xmlDoc.createElement("content")
        txtContent = self.xmlDoc.createCDATASection(content)
        nContent.appendChild(txtContent)
        comment.appendChild(nContent)
        comments.appendChild(comment)

    def addDuplicate(self, bugId):
        if self.xmlDoc.getElementsByTagName("duplicates").length < 1:
            duplicates = self.xmlDoc.createElement("duplicates")
            parent = self.xmlDoc.getElementsByTagName("launchpad-" + self.lptype)[0]
            parent.appendChild(duplicates)
        else:
            duplicates = self.xmlDoc.getElementsByTagName("duplicates")[0]

        duplicateBug = self.xmlDoc.createElement(self.lptype)
        duplicateBug.setAttribute("id", bugId)
        duplicates.appendChild(duplicateBug)

    def addBranch(self, branchname):
        if self.xmlDoc.getElementsByTagName("branches").length < 1:
            branches = self.xmlDoc.createElement("branches")
            parent = self.xmlDoc.getElementsByTagName("launchpad-" + self.lptype)[0]
            parent.appendChild(branches)
        else:
            branches = self.xmlDoc.getElementsByTagName("branches")[0]

        branch = self.xmlDoc.createElement("branch")
        branchTxt = self.xmlDoc.createTextNode(branchname)
        branch.appendChild(branchTxt)
        branches.appendChild(branch)

    def addLinkedBugs(self, bugId, bugTitle):
        if self.xmlDoc.getElementsByTagName("linked_bugs").length < 1:
            linkedBugs = self.xmlDoc.createElement("linked_bugs")
            parent = self.xmlDoc.getElementsByTagName("launchpad-" + self.lptype)[0]
            parent.appendChild(linkedBugs)
        else:
            linkedBugs = self.xmlDoc.getElementsByTagName("linked_bugs")[0]

        linkedBug = self.xmlDoc.createElement("linked_bug")
        bugIdElement = self.xmlDoc.createElement("linked_bug_id")
        bugIdTxt = self.xmlDoc.createTextNode(bugId)
        bugIdElement.appendChild(bugIdTxt)
        bugTitleElement = self.xmlDoc.createElement("linked_bug_title")
        bugTitleTxt = self.xmlDoc.createTextNode(bugTitle)
        bugTitleElement.appendChild(bugTitleTxt)
        linkedBug.appendChild(bugIdElement)
        linkedBug.appendChild(bugTitleElement)
        linkedBugs.appendChild(linkedBug)

    def addWorkItems(self, workItemName, workItemProgress):
        if self.xmlDoc.getElementsByTagName("work_items").length < 1:
            workItems = self.xmlDoc.createElement("work_items")
            parent = self.xmlDoc.getElementsByTagName("launchpad-" + self.lptype)[0]
            parent.appendChild(workItems)
        else:
            workItems = self.xmlDoc.getElementsByTagName("work_items")[0]

        workItem = self.xmlDoc.createElement("work_item")
        workItemNameElement = self.xmlDoc.createElement("work_item_name")
        workItemNameTxt = self.xmlDoc.createTextNode(workItemName)
        workItemNameElement.appendChild(workItemNameTxt)
        workItemProgressElement = self.xmlDoc.createElement("work_item_progress")
        workItemProgressTxt = self.xmlDoc.createTextNode(workItemProgress)
        workItemProgressElement.appendChild(workItemProgressTxt)
        workItem.appendChild(workItemNameElement)
        workItem.appendChild(workItemProgressElement)
        workItems.appendChild(workItem)

    def addMessage(self, created, owner, content, attachment = None):
        if self.xmlDoc.getElementsByTagName("messages").length < 1:
            messages = self.xmlDoc.createElement("messages")
            parent = self.xmlDoc.getElementsByTagName("launchpad-" + self.lptype)[0]
            parent.appendChild(messages)
        else:
            messages = self.xmlDoc.getElementsByTagName("messages")[0]

        message = self.xmlDoc.createElement("message")
        message.setAttribute("created", created)
        message.setAttribute("owner", owner)
        txt = self.xmlDoc.createCDATASection(content)
        message.appendChild(txt)

        if (attachment is not None):
            attachmentNode = self.xmlDoc.createElement("attachment")
            attachmentNode.setAttribute("type", attachment.type)
            attachmentNode.setAttribute("link", attachment.web_link)
            attachmentTitle = self.xmlDoc.createElement("title")
            txt = self.xmlDoc.createTextNode(attachment.title)
            attachmentTitle.appendChild(txt)
            attachmentNode.appendChild(attachmentTitle)
            attachmentFile = self.xmlDoc.createElement("file")

            print "Attachment title: ",attachment.title
            f_in = attachment.data.open()

            # filenames with space, plus and other symbols need to be substituted
            fName = f_in.filename
            fixChars = " +"
            for f in fixChars:
                fName = fName.replace(f, '_')
            print "Attachment filename: ",fName

            fileName = "LPexportBug" + self.xmlDoc.documentElement.getAttribute("id") + "_" + fName

            if not os.path.exists(os.path.normpath(CONST_TEAM + "/attachment")):
                os.makedirs(os.path.normpath(CONST_TEAM + "/attachment"))

            builtName = os.path.normpath(CONST_TEAM + "/attachment/" + fileName)
            if not os.path.exists(builtName):
                f_out = open(builtName, 'wb')
                while 1:
                    copy_buffer = f_in.read(1024*1024)
                    if copy_buffer:
                        f_out.write(copy_buffer)
                    else:
                        break

                f_out.close()

            f_in.close()

            txtFile = self.xmlDoc.createTextNode(fileName)
            attachmentFile.appendChild(txtFile)
            attachmentNode.appendChild(attachmentFile)
            message.appendChild(attachmentNode)

        messages.appendChild(message)

    def addNode(self, name, content, parentName = "launchpad-bug"):
        element = self.xmlDoc.createElement(name)
        txt = self.xmlDoc.createTextNode(content)
        element.appendChild(txt)

        if self.xmlDoc.getElementsByTagName(parentName).length < 1:
            parent = self.xmlDoc.createElement(parentName)
            root = self.xmlDoc.getElementsByTagName("launchpad-" + self.lptype)[0]
            root.appendChild(parent)
        else:
            parent = self.xmlDoc.getElementsByTagName(parentName)[0]

        parent.appendChild(element)

    def addCData(self, name, content, parentName = "launchpad-bug"):
        element = self.xmlDoc.createElement(name)
        txt = self.xmlDoc.createCDATASection(content)
        element.appendChild(txt)
        parent = self.xmlDoc.getElementsByTagName(parentName)[0]
        parent.appendChild(element)

    def getFileName(self, id):
        if self.lptype == "bug":
            return "LPexportBug-" + str(id) + ".xml"
        elif self.lptype == "bp":
            return "LPexportBP-" + str(id) + ".xml" 

    def doesXmlFileExist(self, id, lastUpdated):
        try:
            checkDoc = xml.dom.minidom.parse(os.path.normpath(CONST_TEAM + "/" + self.getFileName(id)))
            print "Found file: " + os.path.normpath(CONST_TEAM + "/" + self.getFileName(id))
        except IOError:
            print "Bug has not been fetched before, id: " + str(id)
            return False
        except:
            return False

        try:
            docLastUpdated = str(checkDoc.getElementsByTagName("date_last_updated")[0].firstChild.nodeValue).replace(' ', 'T')
            lastUpdated = str(lastUpdated).replace(' ', 'T')

            if dateutil.parser.parse(docLastUpdated) == dateutil.parser.parse(lastUpdated):
                print "Bug hasn't changed since last fetched - no need to refetch, id: " + str(id)
                return True
            else:
                print "Bug has been updated since last fetched, id: " + str(id)
                return False
        except:
            return False

    def writeToFile(self, id):
        if not os.path.exists(CONST_TEAM):
            os.makedirs(CONST_TEAM)

        try:
            f = open(os.path.normpath(CONST_TEAM + "/" + self.getFileName(id)), "w")
            f.truncate() 
            f.write(self.xmlDoc.toprettyxml(indent="  ", encoding="utf-8"))
            f.close()
        except Exception, e:
            logging.error("Bug with id " + str(id) + " caused the following error.")
            logging.exception(e)


#----------------------------------------------------------------------------
# start the script
#----------------------------------------------------------------------------

# parse arguments
option_list = [
    # No need to ad '-h' or '-help', optparse automatically adds these options

    optparse.make_option('', '--bug', action='store_true', dest='lpbugs', default=False,
                         help='Process Launchpad Bugs'),
    optparse.make_option('', '--bp', action='store_true', dest='lpbps', default=False,
                         help='Process Launchpad Blueprints')
]

usage = 'usage: %prog [-h|--help|<options>]'
parser = optparse.OptionParser(usage=usage, option_list=option_list)

# OptionParser gets the options out, whatever is not preceeded by
# an option is considered args.
(options, args) = parser.parse_args()

# we are not expecting args right now
if args:
    parser.error('Invalid argment(s) found: ' + str(args))

# check options
if not options.lpbugs and not options.lpbps:
    parser.print_help()
    sys.exit(1)
elif options.lpbugs:
    print "INFO: Processing Launchpad Bugs ..."
    Bug()
elif options.lpbps:
    print "INFO: Processing Launchpad Blueprints ..."
    Blueprint()

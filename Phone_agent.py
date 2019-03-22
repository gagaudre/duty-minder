#!/usr/bin/env python2

################################################################################
#
# Phone_Agent - Query PagerDuty every now and then (through cron) and
#               en/disable the appropriate support phone extension according to
#               the PagerDuty schedule.
#
# Functionality based on Avaya EC500 feature. Other phone system's remote controller feature have not been tested.
#
# PROD Invocation from cron:
# */5 * * * * root [ ! -x /opt/tools/phone_agent/Phone_Agent.py ] && chmod 744 /opt/tools/phone_agent/Phone_Agent.py; \\
# /opt/tools/phone_agent/Phone_Agent.py /opt/tools/phone_agent/Phone_Agent.conf now now >> /opt/tools/phone_agent/Phone_Agent.log 2>&1
#
# TEST Invocation from CLI (test mode):
#   (Note: test invocation [-t] We will not call out. Better used with the '-d' [debug] option as well, as shown here)
# /opt/tools/phone_agent/Phone_Agent.py -dt /opt/tools/phone_agent/Phone_Agent.conf '2018-09-14T09:00:00-08:00' 0
#
################################################################################

import  os, sys, argparse, commands, time
import  re, json, requests
import  logging,  logging.config
import  socket
import  ConfigParser
import  datetime
import  dateutil.parser
import  boto

from    dateutil.relativedelta  import *
from    pytz                    import timezone
from    twilio.rest             import TwilioRestClient
from    urllib                  import quote_plus

################################################################################
def setupLogging(loglevel=logging.INFO):
    """ Set up the Dictionary-Based Configuration For Logging """

    # The following configures two loggers, the root logger and a logger named "phone_ctlr_log". Messages sent to the
    # root logger will be sent to the system log using the syslog protocol, and messages to the "phone_ctlr_log" logger will
    # be written to the Phone_Agent.log file which will be rotated once the log reaches 1Mb.

    configdict = {
        'version': 1,                        # Configuration schema in use; must be 1 for now
       #'disable_existing_loggers': True,    # Disables all existing logging configurations

        'formatters': {
            'brief': {
                'format' : '%(levelname)-8s %(asctime)s (%(created)s) %(message)s',
                'datefmt': '%Y%m%dT%H%M%S.%Z' },
            'standard': {
                'format' : '%(levelname)-8s %(asctime)s %(name)-15s %(message)s',
                'datefmt': '%Y%m%dT%H%M%S.%Z' },
            'console': {
                'format' : '%(levelname)-8s %(asctime)s -- %(message)s',
                'datefmt': '%Y%m%dT%H%M%S.%Z' },
            'custom': {
                'format' : '%(asctime)s - %(message)s',
                'datefmt': '%Y-%m-%dT%H:%M:%S.%Z' }         ### Ex,: 2038-01-01T05:05:02
        },

        'handlers': {'applog': {'class': 'logging.handlers.RotatingFileHandler',
                                'filename': '/opt/tools/phone_agent/Phone_Agent.log',
                               #'filename': 'Phone_Agent.log',
                                'backupCount': 3,
                                'formatter': 'custom',
                                'level': 'INFO',
                                'maxBytes': 1024*1024},
                     'conlog': {'class': 'logging.StreamHandler',
                                'formatter': 'console',
                               #'stream': 'console',
                                'level': 'DEBUG'},
                     'syslog': {'class': 'logging.handlers.SysLogHandler',
                                'formatter': 'standard',
                                'level': 'ERROR'}},

        # Specify all the subordinate loggers
        'loggers': {
                    'phone_ctlr_log': {
                                'handlers': ['applog']
                    },
                    'console_log': {
                                'handlers': ['conlog']
                    }
        },
        # Specify properties of the root logger
        'root': {
                 'handlers': ['syslog']
        },
    }

    # Set up configuration
    logging.config.dictConfig(configdict)


################################################################################
def phone_controller(client_account, client_token, mode, extension, debug=False, test_mode=False):
    """ Call the Phone_Ctlr remote setup line to en/disable call forwarding for the specific extension """

    #-- Build the DTMF tones string to send to en/disable Phone_Ctlr ...
    phone_ctlr_enable  = "121w%d#%d#"
    phone_ctlr_disable = "122w%d#%d#"
    if mode == 'enable':  digits =  phone_ctlr_enable  % (extension, extension)
    if mode == 'disable': digits =  phone_ctlr_disable % (extension, extension)
    if args.debug:
        clogger.info( "mode: %-7s, digits: %s" % ( mode, digits) )

    if test_mode:
        clogger.info( "In test mode. We will not be using the phone_controller (%s) function to call out..." % phone_ctlr_number )
        return True
    else:
        #-- Call to en/disable Phone_Ctlr ...
        if args.debug:
            clogger.info( "Calling the Phone_Ctlr control number (%s) with the Twilio client ... digits: %s" % (phone_ctlr_number, digits) )

        try:
            call = client.calls.create(        to  = phone_ctlr_number,
                                            from_  = callerid,
                                       send_digits = digits,            # Example: "122w19876#19876#"
                                           timeout = int(10),
                                               url = "http://twimlets.com/%s/end" % client_account
            )   # End of call Twiml
        except:
            clogger.error("Unable to complete the call to the Phone Controller.")

#        call_details_url = 'https://api.twilio.com/2010-04-01/Accounts/%s/Calls/%s.json' % (client_account, call1.sid)
#        try:
#            call_details_req = requests.post(call_details_url, auth=(client_account, client_token))
#
#        except requests.RequestException: print "There was an ambiguous exception that occurred while handling your request."
#        except requests.ConnectionError:  print "A Connection error occurred."
#        except requests.HTTPError:        print "An HTTP error occurred."
#        except requests.URLRequired:      print "A valid URL is required to make a request."
#        except requests.TooManyRedirects: print "Too many redirects."
#
#        call_details = json.loads(call_details_req.content)
#
#        print json.dumps(call_details, sort_keys=True, separators=(', ', ': '), indent=2)

       #clogger.info( "Sid: %s" % call.sid )
        return call.sid


################################################################################
def send_email(ses, email, error_msg, error_result=None, error_solution=None):

    hst_name = str(socket.gethostname())
    subject  = "OPS Automation -- On-call Phone Switcher Script - Error"

    m  = "<p align= center>An error occured in the Phone_Ctlr switchover script.</p>\n"
    m += "<hr />\n"
    m += error_msg
    m += "<p>\n"
    m += "<hr />\n"
    m += "<p>If you have any questions, please email the <a href='mailto:sysEng@my_company.com'>script owner</a></p>\n"
    m += "<p><font size=\"-1\"><i>This message was generated on %s. " % hst_name
    m += "Script name: %s</i></font></p>" % os.path.abspath(__file__)

    try:
        ses.send_email("opsTeam@saasmail.my_company.com", subject, None, [email, "sysEng@my_company.com"], format = "html", html_body = m)
        return True

    except Exception, e:
        print "Failed to send mail to %s: %s %s" % (email, Exception, e)
        alogger.error( "Failed to send mail to %s: %s %s" % (email, Exception, e) )
        return False

################################################################################
def get_phone_numbers(team_member, direction):
    """ Get the Desk phone number for the Team member (5xxxx) """

    try:
        desk_phone = int(s.get('desk_phone', team_member))
        cell_phone = int(s.get('cell_phone', team_member))
        return (desk_phone, cell_phone)

    except Exception, e:
        alogger.error("Config file: Phone_Agent.conf does not contain a phone number for: %s" % team_member)
        first_name = team_member.split()[0]

        send_email(ses,
                   email,
                   "<dl><dt><b>Error:</b></dt><dd>The config file: Phone_Agent.conf does not contain phone numbers for: %s.</dd>\
                    <dt><b>Result:</b></dt><dd>Phone_Ctlr was NOT switched over %s %s.</dd>\
                    <dt><b>Solution:</b></dt><dd>PLS add %s's phone numbers to the config file: <i>%s/Phone_Agent.conf</i></dd></dl>" %
                        (team_member, direction, first_name, first_name, os.path.dirname(os.path.abspath(__file__)))
        )

        sys.exit(1)

################################################################################
def get_pd_schedule(schedId, ts_in=None, ts_out=None, debug=False):  # ts_... => Timestamps ...
    """ Extract the PagerDuty schedule for the specified PD_group for the datetime_range specified by ts_in/ts_out """

    sch_beg = sch_end = 0

    if args.debug:
        print "\nEntering function with:                 \nts_in:   %s\nts_out:  %s\n" % (ts_in, ts_out)    # debug
        print "1-type(ts_in):  ", ; print type(ts_in)   # debug
        print "1-type(ts_out): ", ; print type(ts_out)  # debug

    ############################################################################
    # Use current time if timestamp range not specified ...
    ############################################################################
    now1 = dateutil.parser.parse(commands.getoutput("date +%Y-%m-%dT%H:%M:%S%:z"))
    if args.debug:
        print "Now1: %s" % now1
       #print "Now1: %s" % now1.strftime("%Y-%m-%dT%H:%M:%S%z")   # debug

    ### ts_in is null or == '0' or == 'now' ...
    if not ts_in  or ts_in.lower()  == 'now' or ts_in  == '0':
        ts_in  = now1
        if args.debug: print "\n2-Timestamps=='now' or 0 or null, using current time:\nts_in:  %s\n" % (ts_in) # debug
    else: ts_in = dateutil.parser.parse(ts_in)

    ### ts_out is null or == '0' or 'now' ...
    if not ts_out or ts_out.lower() == 'now' or ts_out == '0':
        ts_out = now1
        if args.debug: print "\n2-Timestamps=='now' or 0 or null, using current time:\nts_out: %s\n" % (ts_out)    # debug
    else: ts_out = dateutil.parser.parse(ts_out)

    if args.debug:
        print "2-type(ts_in):  ", ; print type(ts_in)   # debug
        print "2-type(ts_out): ", ; print type(ts_out)  # debug

    ############################################################################
    ### Build the PagerDuty API URL with specific schedule start/stop datetime (include whole shift) ...
    ############################################################################
    url = "https://my_company.pagerduty.com/api/v1/schedules/%s/entries?since=%s&until=%s&overflow=true" % (
                                                schedId,
                                                ts_in.strftime('%Y-%m-%dT%H:%M:%S%z'),
                                                ts_out.strftime('%Y-%m-%dT%H:%M:%S%z'))
    if args.debug:
        print "URL: %s" % url   # debug

    ############################################################################
    ### Query the pager Duty service (upto 5 times if necessary) ...
    ############################################################################
    for x in xrange(1,5):
        try:
            if args.debug:
                print "Trying PagerDuty url. Attempt no: %s" % x   # debug
            r = requests.get(url, auth=('pagerdutyapiuser@my_company.com', 'my_company12345678'))  # my_company12345678 => PD-Token
            break
        except Exception, e:
            alogger.warning( "Warning - PagerDuty API connection problem (attempt: %s of 5): %s %s" % (x, Exception, e) )
            try:
                send_email(ses, email, e)
            except Exception1, ex1:
                print "Failed to send mail to %s: %s %s" % (email, Exception1, ex1)
    else: ### Bail out if too stubborn ...
        alogger.error( "Error - Cannot recover from PagerDuty API connection problem (after trying %s/5): %s %s" % (x, Exception, e) )
        sys.exit(1)

    content = json.loads(r.content)

    if args.debug:
        print json.dumps(content, sort_keys=True, separators=(', ', ': '), indent=4)  # debug
        #print json.dumps(json.load(f1), sort_keys=True, separators=(', ', ': '), indent=4)  # debug
        #-OR-
        #s = json.dumps(json.loads(r.content), sort_keys=True, separators=(', ', ' : '), indent=4)
        #print '\n'.join([l.rstrip() for l in  s.splitlines()])

    if content.has_key("error"):
        send_email(ses, email,
                   "<dl><dt><b>Error:</b></dt><dd>Couldn't connect to PagerDuty: %s.</dd>\
                   <dt><b>Result:</b></dt><dd>Phone_Ctlr was NOT switched over.</dd>\
                   <dt><b>Troubleshooting:</b></dt><dd>Review connectivity to PagerDuty URL:<br />%s</dd></dl>" % (str(content.get("error").get("message")), url)
        )

       #send_email(ses, email,
       #           "Couldn't connect to PagerDuty: %s."                            % str(content.get("error").get("message")),
       #           "Result: Phone_Ctlr was NOT switched over.",
       #           "Troubleshooting: Review connectivity to PagerDuty URL:<br />%s" % url
       #)

        sys.exit(2)

    ############################################################################
    ### If 'total entries' >1: this means it is time to switch Phone_Ctlr ...
    ############################################################################
    if content.get('total') > 1:
        if args.debug:
            print "Time to change Phone_Ctlr setup"
    else:
        if args.debug:
            print "Wait to change Phone_Ctlr setup"

    who1 = who2 = None
    cnt=0

    for entry in content.get('entries'): # From URL
        if args.debug:
            print "\nEntry " + str(cnt) # debug
            print "Name: %-20s (Id: %8s) -- Start: %s -> End: %s" % (entry.get('user').get('name'),   # debug
                                                                     entry.get('user').get('id'),     # debug
                                                                     entry.get('start'),              # debug
                                                                     entry.get('end'))                # debug
        if cnt == 0: who1 = entry.get('user').get('name')
        who2 = who1
        if cnt == 1: who2 = entry.get('user').get('name')
        cnt += 1

    sch_beg = str(dateutil.parser.parse(entry.get('start')))
    sch_end = str(dateutil.parser.parse(entry.get('end')))

    return (who1, who2, sch_beg, sch_end)

#################
##    MAIN
#################

if __name__ == '__main__':

    VERSION='0.1'

    parser = argparse.ArgumentParser(description = "Phone Line Redirector for Phone_Ctlr", add_help=True, version=VERSION)
    parser.add_argument('conf_file',       action='store',      default="Phone_Agent.conf",    help = "Phone extension conf file")
    parser.add_argument('start_datetime',  action='store',                     help = "Begining of coverage")
    parser.add_argument('end_datetime',    action='store',                     help = "End of coverage")
    parser.add_argument('--verbose',       action='store_true', default=False, help = "Show verbose output")
    parser.add_argument('-l', '--lookahead',  action='store',      default=int(8),help = "Lookahead before and after current time")
    parser.add_argument('-d', '--debug',   action='store_true', default=False, help = "Show debug info")
    parser.add_argument('-t', '--test',    action='store_true', default=False, help = "Test mode - Does not call out")
   #parser.add_argument('-V', '--version', action='version',   version='%(prog)s: 1.0')
    args = parser.parse_args()

    email = "opsTeam@saasmail.my_company.com"

    ############################################################################
    ### Initialize logging ...
    ############################################################################
    setupLogging()

    alogger = logging.getLogger("phone_ctlr_log")
    clogger = logging.getLogger("console_log")
    alogger.setLevel(logging.INFO)
    if args.debug:
        alogger.setLevel(logging.DEBUG)
        clogger.setLevel(logging.DEBUG)

    ############################################################################
    ### Read the configuration file ...
    ############################################################################
    s = ConfigParser.ConfigParser()
    s.readfp(open(args.conf_file))
    ses = boto.connect_ses(s.get("awsprod", "access_key"), s.get("awsprod", "secret_key"))  # Establish a boto session ...

    try:
      pagerduty_schedule_id = s.get("awsprod","pagerduty_schedule_id")
    except:
      alogger.error( "Missing pagerduty_schedule_id value in the config file")
      send_email(ses,
                 email,
                 "<dl><dt><b>Error:</b></dt><dd>Phone_Ctlr might be in an inconsistent state. Missing pagerduty_schedule_id value in the config file.</dd>\
                  <dt><b>Result:</b></dt><dd>Phone_Ctlr might not be set to escalate to the correct person.</dd>\
                  <dt><b>Solution:</b></dt><dd>PLS manually turn on Phone_Ctlr (<a href=\"https://docs.my_company.com/Phone_Ctlr+Cheat+Sheet\">cheat sheet</a>)<br>You can also check the log file <i>%s:/opt/tools/phone_agent/Phone_Agent.log</i></dd></dl>" %
                      (str(socket.gethostname()), )
      )

    ############################################################################
    #-- Twilio REST API version ...
    ############################################################################
    apibase = "https://api.twilio.com/"
    apivers = "2010-04-01"

    ############################################################################
    ### Read the Twilio credentials ...
    ############################################################################
    tw_acct  = s.get('twilio', 'account')
    tw_token = s.get('twilio', 'token')

    ############################################################################
    #-- Outgoing Caller ID you have previously validated with Twilio ...
    ############################################################################
    callerid           = "+18005551212"    # My_Company originating phone number - Twilio verified ...
    phone_ctlr_number  = "+18005551212"    # Phone_Ctlr phone number to hit to en/disable Phone_Ctlr remotely - Twilio verified ...

    ############################################################################
    ### Let's run everything localized ...
    ############################################################################
    os.environ["TZ"] = "PST8PDT"
    if args.debug: os.system("date +'%nCurrent: %Y-%m-%dT%H:%M:%S%z'") # Display localized system's datetime.

    ############################################################################
    #-- Instantiate a new Twilio Rest Client ...
    ############################################################################
    client = TwilioRestClient(account=tw_acct, token=tw_token, base=apibase, version=apivers)

    if not args.start_datetime  or args.start_datetime.lower()  == 'now' or args.start_datetime  == '0':
        now1 = datetime.datetime.now()
    else:
        now1 = dateutil.parser.parse(args.start_datetime) # First command line argument ...

    now1_iso = now1.strftime('%Y-%m-%dT%H:%M:%S%Z') # String representation of current time ...
    if args.debug:
        print "now1:    %s" % now1_iso
        print "now1 type: ", ; print type(now1) # debug
        print "now1_iso type: ", ; print type(now1_iso) # debug

    ############################################################################
    ### Calculate 'args.lookahead' (default=8) minutes before and after current time (default=16-minutes window) ...
    ### This allows the OPS schedule to be changed to almost any time and the script to catch any failed telephone call ...
    ############################################################################
    nowminus = (now1 + relativedelta(minutes=-int(args.lookahead))).strftime('%Y-%m-%dT%H:%M:%S%z')
    nowplus  = (now1 + relativedelta(minutes=+int(args.lookahead))).strftime('%Y-%m-%dT%H:%M:%S%z')
    if args.debug:
        print "nowminus:   %s" % nowminus
        print "nowplus:    %s" % nowplus

    ############################################################################
    ### Query Pager Duty for the current state of affairs ...
    ############################################################################
    ### who1 = on-call exiting  schedule ...
    ### who2 = on-call entering schedule ...
    ############################################################################
    who1, who2, begin1, end1 = get_pd_schedule(pagerduty_schedule_id, nowminus, nowplus, args.debug)

    if args.debug:
        print "\nwho1, who2, begin1, end1: %-30s, %-30s, %s, %s" % (who1, who2, begin1, end1)

    if who1 != who2:    # time to swap on-call responsibilities ...
        alogger.info( "Switching Phone_Ctlr from %-17s to %-17s" % (who1, who2) )

        ### Query the configuration for phone extension ...
        (desk1, cell1) = get_phone_numbers(who1, "from")    # For person leaving  on-call duty ...
        (desk2, cell2) = get_phone_numbers(who2, "to")      # For person entering on-call duty ...
        cell1          = re.sub('^', '+1', re.sub('^1', '', re.sub(r'\D', '', str(cell1))))   ### Cleanup the cell phone from the config file: +1AAANNNXXXX
        cell2          = re.sub('^', '+1', re.sub('^1', '', re.sub(r'\D', '', str(cell2))))
        extended_desk1 = re.sub(r'^7', '+1408540', str(desk1))  ### Figure out the long extension number from the potentially short version of it.
        extended_desk2 = re.sub(r'^7', '+1408540', str(desk2))
        firstname_who1 = who1.split()[0]    ### Extract first name from complete name
        firstname_who2 = who2.split()[0]

        #####################################################
        ### Initiate the call out using the Twilio client ...
        #####################################################
        if args.debug: print "\n",

        local_timezone = timezone('US/Pacific')
        localtime = datetime.datetime.now(local_timezone)

        passive_oncall = False
        exiting_passive_oncall = False

        if (localtime.hour >= 23 or localtime.hour < 7) or (localtime.hour == 22 and localtime.minute > 45):
          passive_oncall = True
          alogger.info("Passive on-call: %s" % localtime)
        elif (localtime.hour == 7 and localtime.minute < 15):
          exiting_passive_oncall = True
          alogger.info("Exiting passive on-call: %s" % localtime)
        else:
          alogger.info("Active on-call: %s" % localtime)


        if passive_oncall:
          sid2 = True
        else:
          ### Enable first, then disable, making sure someone receive the escalation call if any ...
          sid2 = phone_controller(tw_acct, tw_token, 'enable',  desk2, args.debug, args.test) # enable  the new on-call phone ...
          time.sleep(5) ### Give Phone_Ctlr the time to finalize the first Phone_Ctlr switch ...


        sid1 = phone_controller(tw_acct, tw_token, 'disable', desk1, args.debug, args.test) # disable the old on-call phone ...
        time.sleep(25) ### Give Phone_Ctlr the time to switch between extensions before calling the desk phone ...

        if args.debug:
            print "\n",
            print "Extension number:  ", ; print s.get('desk_phone', who1)
            print "Phone_Ctlr_disable:", ; print "122w%s#%s#" % (desk1, desk1) # 122w12345#12345#
            print "Extension number:  ", ; print s.get('desk_phone', who2)
            print "Phone_Ctlr_enable: ", ; print "121w%s#%s#" % (desk2, desk2) # 121w19876#19876#

        #####################################################
        ### Call out to confirm switchover succeeded ...
        #####################################################

        if sid1 and sid2:   ### Both calls to Phone_Ctlr were successful.
            """ At this point, we have a good feeling that Phone_Ctlr switchover is successful.
                Now, all is left to do, is to inform both people: 'who1' is leaving, 'who2' is entering on-call.
            """
            if args.test:
                print "Would call the desk extension of %-10s (%s) to confirm the switch." % (firstname_who2, extended_desk2)
            else:
                if passive_oncall:
                  print "Skipping the call to the new person (passive on-call)"
                else:
                  try: ### Call out to the new on-call person through desk phone (using Phone_Ctlr) ...
                      url2_string = "http://twimlets.com/echo?Twiml=<Response><Say>Hello %s, this is the Phone Monkey from My_Company.  The support extension has been enabled for your phone.  You are officially on-call.  Have a good one! Good bye!</Say></Response>" % firstname_who2
                      url2 = quote_plus(url2_string, ':/?=')
                      if args.debug:
                          print "url2_string = %s\nurl2 = %s" % (url2_string, url2)

                      call = client.calls.create(to      = cell2,   # person who is entering on-call ... using the desk phone.
                                                 from_   = callerid,
                                                 timeout = int(10),
                                                 url     = url2
                      )
                      alogger.info(  "Success calling %-10s at %s -- Call sid: %s" % (firstname_who2, extended_desk2, call.sid) )
                  except:
                      alogger.error( "Failed  calling %-10s at %s -- Unable to complete the call" % (firstname_who2, extended_desk2) )

                  time.sleep(20) ### debug

                if exiting_passive_oncall:
                  print "Skipping the call to the person leaving (passive on-call)"
                else:
                  try: ### Next: the person leaving on-call (using the cell phone) ...
                      url1_string = "http://twimlets.com/echo?Twiml=<Response><Say voice=\"woman\">Hello %s, this is the Phone Monkey from  My_Company. The support extension switchover was successful.  You are now off-duty.  Take it easy! Good bye!</Say></Response>" % firstname_who1
                      url1 = quote_plus(url1_string, ':/?=')
                      if args.debug:
                          print "url1_string = %s\nurl1 = %s" % (url1_string, url1)
                      call = client.calls.create(to      = cell1,   # Using the cell phone.
                                                 from_   = callerid,
                                                 timeout = int(10),
                                                 url     = url1
                      )
                      alogger.info(  "Success calling %-10s at %s -- Call sid: %s" % (firstname_who1, cell1, call.sid) )
                  except:
                      alogger.error( "Failed  calling %-10s at %s -- Unable to complete the call" % (firstname_who1, cell1) )

        else:   ### Something happened: Phone_Ctlr is in an unknown state ...
        #####################################################
        ### Call out to the previous on-call person to troubleshoot ...
        #####################################################
            if args.test:
                print "Would call the cell phones of %-10s (%s) and %-10s (%s) to inform of the problem." % (firstname_who1, cell1, firstname_who2, cell2)
            else:

                try: ### The person who was on-call ...
                    url2_string = "http://twimlets.com/echo?Twiml=<Response><Say>Hello %s, this is Romeo from My_Company reporting an error. The Phone_Ctlr might be in an inconsistent state. Please contact %s, the new on-call person, to troubleshoot. Thank you.</Say></Response>" % (firstname_who1, firstname_who2)
                    url2 = quote_plus(url2_string, ':/?=')
                    if args.debug:
                        print "url2_string = %s\nurl2 = %s" % (url2_string, url2)
                    call = client.calls.create(to     = cell1,   # person who WAS on-call ... using the cell number since Phone_Ctlr might be broken.
                                               from_  = callerid,
                                               timeout= int(10),
                                               url    = url2
                    )
                    alogger.info(  "Success calling %-10s at %s -- Call sid: %s" % (firstname_who1, cell1, call.sid) )
                except:
                    alogger.error( "Unable to complete the call out to the previous on-call person." )

                time.sleep(25)
                try: ### The person entering his on-call duty ...
                    url1_string = "http://twimlets.com/echo?Twiml=<Response><Say voice=\"woman\">Hello %s, this is Juliette from My_Company reporting an error. The Phone_Ctlr might be in an inconsistent state. Please contact %s, the previous on-call person, to troubleshoot. Thank you.</Say></Response>" % (firstname_who2, firstname_who1)
                    url1 = quote_plus(url1_string, ':/?=')
                    if args.debug:
                        print "url1_string = %s\nurl1 = %s" % (url1_string, url1)
                    call = client.calls.create(to     = cell2,   # person who IS NOW on-call ... using the cell number since Phone_Ctlr might be broken.
                                               from_  = callerid,
                                               timeout= int(10),
                                               url    = url1
                    )
                    alogger.info(  "Success calling %-10s at %s -- Call sid: %s" % (firstname_who2, cell2, call.sid) )
                except:
                    alogger.error( "Unable to complete the call out to the new on-call person." )

                send_email(ses,
                           email,
                           "<dl><dt><b>Error:</b></dt><dd>Phone_Ctlr might be in an inconsistent state.</dd>\
                            <dt><b>Result:</b></dt><dd>Phone_Ctlr might not be set to escalate to the correct person.</dd>\
                            <dt><b>Solution:</b></dt><dd>PLS manually turn on Phone_Ctlr (<a href=\"https://docs.my_company.com/Phone_Ctlr+Cheat+Sheet\">cheat sheet</a>)<br>You can also check the log file <i>%s:/opt/tools/phone_agent/Phone_Agent.log</i></dd></dl>" %
                                (str(socket.gethostname()), )
                )

    else:
       #print "%s - Not time to switch yet. %-17s is still on-call. We will check back 5 minutes from now." % (now1_iso, who1)
        alogger.info( "%-17s is still on-call. We will check back 5 minutes from now." % who1 )




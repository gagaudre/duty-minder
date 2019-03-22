Phone_Agent - Query PagerDuty every now and then (through cron) and
              en/disable the appropriate support phone extension according to
              the PagerDuty schedule.
PROD Invocation from cron:
*/5 * * * * root [ ! -x $INST_DIR/Phone_Agent.py ] && chmod 744 $INST_DIR/Phone_Agent.py; \\
$INST_DIR/Phone_Agent.py $INST_DIR/Phone_Agent.conf now now >> $INST_DIR/Phone_Agent.log 2>&1
TEST Invocation from CLI (test mode):
  (Note: test invocation [-t] We will not call out. Better used with the '-d' [debug] option as well, as shown here)
$INST_DIR/Phone_Agent.py -dt $INST_DIR/Phone_Agent.conf '2018-09-14T09:00:00-08:00' 0
       call_details_url = 'https://api.twilio.com/2010-04-01/Accounts/%s/Calls/%s.json' % (client_account, call1.sid)
       try:
           call_details_req = requests.post(call_details_url, auth=(client_account, client_token))
       except requests.RequestException: print "There was an ambiguous exception that occurred while handling your request."
       except requests.ConnectionError:  print "A Connection error occurred."
       except requests.HTTPError:        print "An HTTP error occurred."
       except requests.URLRequired:      print "A valid URL is required to make a request."
       except requests.TooManyRedirects: print "Too many redirects."
       call_details = json.loads(call_details_req.content)
       print json.dumps(call_details, sort_keys=True, separators=(', ', ': '), indent=2)


Support team Members - Phone_Ctlr telephone numbers
When adding a new user, make sure the Phone_Ctlr feature is enabled
on his deskphone or softphone by creating a helpdesk ticket.
Make sure there is only one instance of Phone_Ctlr running.
AWS Account


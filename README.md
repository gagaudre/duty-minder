# duty_minder  --  Phone_Agent

## Description
Queries PagerDuty every now and then and en/disable the appropriate support phone extension according to the PagerDuty schedule.
## Installation
Install all files in the same directory ($INST_DIR).
## Configuration

#### Tokens & Support team phone numbers
Update the config file with your information.<br/>
When adding a new user, make sure the call forwarding feature is enabled
on her/his deskphone or softphone to allow proper forwarding.<br/>

## Usage
#### PROD Invocation
From cron:<br/>
<code>*/5 * * * * phoneagent [ ! -x $INST_DIR/Phone_Agent.py ] && \\<br/>
chmod 744 $INST_DIR/Phone_Agent.py; \\<br/>
$INST_DIR/Phone_Agent.py $INST_DIR/Phone_Agent.conf now now >> \\<br/>$INST_DIR/Phone_Agent.log 2>&1
</code>
#### TEST Invocation from the command line
Note: By using the test option [-t], we will not call out.<br/>
This is better used with the '-d' [debug] option as well (as shown here):<br/>
<code>
$INST_DIR/Phone_Agent.py -dt $INST_DIR/Phone_Agent.conf '2018-09-14T09:00:00-08:00' 0
</Code>

#### Running one instance
Also, make sure there is only one instance of Phone_Agent running.

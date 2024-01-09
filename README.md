# Solaredge Forecast integration

Home assistant custom integration that forecasts the overall solar energy production over a specified timeframe
using historical data from SolarEdge. The integration is using the 
[Solaredge library](https://pypi.org/project/solaredge/).

NOTE: To forecast the overall solar energy production over a period of time, there must be a minimum of 1 year of 
historical data available for each month within that period.

## How to install

1. Make sure you have [hacs](https://hacs.xyz/) installed
2. In the HACS panel search for 'Solaredge forecast' and click on the orange download button.
3. Reboot HA
4. In HA goto Config -> Integrations. Add the Solaredge-Forecast integration to HA.
5. In your lovelace dashboard, add a card with the Solaredge-Forecast entities.

## Options

The Solaredge Forecast integration has the following options:

**Site id**

The ID of the solar installation. You can find the ID at the Solaredge web portal.
Go to https://monitoring.solaredge.com and login with your Solaredge account. Then go to Admin >> Site access >> API access

**Account key**

The api key which you can find at the same place as the site ID

**Startday of the forecast period**

Day of the month from which the total energy will be summed.  

**Startmonth of the forecast period**

Month from which the total energy will be summed. If the startdate is after the current date the
previous year is used for the startdate. If the startdate is before the current date the current year will be used.

**Endday of the forecast period**

Day of the month for which the total energy will be predicted.  

**Endmonth of the forecast period**

Month of the month for which the total energy will be predicted. If the enddate is after the current date the
current year is used for the enddate. If the enddate is before the current date the next year will be used.

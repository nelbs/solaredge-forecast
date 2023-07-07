# Solaredge Forecast integration

Home assistant component that forecasts the total solar energy generation for a specified time period by using the [solaredge library](https://pypi.org/project/solaredge/)

## How to install

1. Make sure yo have [hacs](https://hacs.xyz/) installed
2. Add this repository as custom repository to hacs by going to hacs, integrations, click on the three dots in the upper right corner and click on custom repositories.
3. In the repository field, fill in the link to this repository (https://github.com/nelbs/solaredge-forcast) and for category, select `Integration`. Click on `Add`
4. Go back to hacs, integrations and add click on the blue button `Exlore and download repositories` in the bottom left corner, search for `Solaredge Forecast` and install it 
5. Reboot HA
6. In HA goto Config -> Integrations. Add the Solaredge-Forecast integration to HA.
7. In your lovelace dashboard, add a card with the Solaredge-Forecast entities.

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

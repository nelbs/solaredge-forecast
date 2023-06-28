"""Module to make a forecast for the solar energy production"""
from datetime import datetime
import solaredge
import pandas as pd

class SolaredgeForecast(object):
    """Solaredge forecast data"""
    def __init__(self, startdate, enddate, site_id, account_key):
        self.startdate = datetime.strptime(startdate, '%Y%m%d').date()
        self.enddate = datetime.strptime(enddate, '%Y%m%d').date()
        self.site_id = site_id
        self.account_key = account_key

        data = self.get_solar_forecast()

        self.solaredge_estimated = data["Solar energy estimated"]
        self.solaredge_produced = data["Solar energy produced"]
        self.solaredge_forecast = data["Solar energy forecast"]
        # self.last_update = data["last_update"]

    def get_solar_forecast(self):
        """Calculate solar energy forecast."""

        now = datetime.now()

        # connect to Solaredge API
        data = solaredge.Solaredge(self.account_key)

        # Get date when production started
        start_production = data.get_data_period(site_id=self.site_id)["dataPeriod"]["startDate"]

        # Get energy production per month from production start till now and store in dataframe
        energy_month_average = data.get_energy(site_id=self.site_id,
                                               start_date=start_production,
                                               end_date=self.enddate,
                                               time_unit="MONTH")
        df = pd.DataFrame(energy_month_average['energy']['values'])
        df.rename(columns={'value': 'energy'}, inplace=True)
        df = df[df.energy != 0]
        # change wh to Kwh
        df['energy'] = df['energy'].apply(lambda x: x / 1000)
        # change stringdate to datetime object
        df['date'] = df['date'].apply(lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S').date())
        # Add columns for year and month from datetime
        df['year'] = pd.DatetimeIndex(df['date']).year
        df['month'] = pd.DatetimeIndex(df['date']).month
        df.drop(columns=['date'])
        df = df[['year', 'month', 'energy']]

        # Find the average daily energy production by considering the average monthly energy production.
        average_production = {}
        for i in range(1, 13):
            number_of_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            average_production[i] = (df.loc[df['month'] == i, 'energy'].mean() / number_of_days[i - 1])

        # Get total energy production from start date till now
        energy_produced = round(data.get_time_frame_energy(site_id=self.account_key,
                                                           start_date=self.startdate,
                                                           end_date=self.enddate,
                                                           time_unit="YEAR")
                                ['timeFrameEnergy']['energy'] / 1000)

        # Create dataframe with all future days within the provided period (now till enddate)
        df2 = pd.DataFrame(pd.date_range(start=now.date(), end=self.enddate), columns=['date'])
        # Add columns for year, month and day
        df2['year'] = pd.DatetimeIndex(df2['date']).year
        df2['month'] = pd.DatetimeIndex(df2['date']).month
        df2['day'] = pd.DatetimeIndex(df2['date']).day
        df2.drop(columns=['date'])
        df2 = df2[['year', 'month', 'day']]

        # Fill the dataframe with energy values for each day
        df2['energy'] = df2['month'].map(average_production)
        energy_estimated = round(df2['energy'].sum())

        # Calculate the solar energy forecast
        forecast = energy_produced + energy_estimated

        data = {}
        data["Solar energy produced"] = energy_produced
        data["Solar energy estimated"] = energy_estimated
        data["Solar energy forecast"] = forecast

        return data

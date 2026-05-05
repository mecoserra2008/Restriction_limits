import blpapi
import pdblp
import pandas as pd
import numpy as np

con = pdblp.BCon(debug=False, port= 8194, timeout=5000)
con.start()

tickers=[] #These will be the tickers that we have on the Portfolio
#Static part of the bonds
static_fields=[
  'Maturity',
  'CPN',
  'INDUSTRY_SECTOR',
  'CRNCY',
  'BB_COMPOSITE',
  'AMT_OUTSTANDING',
]


static= con.ref(tickers, static_fields)
#Fluctuating characteristics of the bond

ts_fields=[
  'PX_LAST',
  'DUR_ADJ_MID',
  'CONVEXITY_MID',
  'Z_SPREAD_MID',
  'OAS_SPREAD_MID',
  'YLD_YTM_MID',
  'PX_VOLUME',
]

ts_data= con.bdh(tickers, ts_fields,start,end)

prices=ts_data['PX_LAST'].unstack('ticker')
positions= pd.Series({'':,})#This is not done, we should be checking here the positions in which we are in right now and  get the notional positions

V= prices.multiply(positions/100)
delta_V= V.diff()
log_delta_V=np.log(V).diff() #log should be the delta(log(x)) and not log(delta(x))

macro_tickers = {
  '':,
  '':,
}

macro=con.bdh(list(macro_tickers.values()),
             ['PX_LAST'],start,end)
macro_ret= np.log(macro['PX_LAST'].unstack().diff())

macro_ret.columns=list(macro_ticker.keys())

'''
There are effectively 2 options to calculate the implied CDS:
'''

#OPTION A)
cds_tickers=['','...']
h=con.bdh(cds_tickers,['PX_LAST'],start,end)
#S_it=exp(-lambda_it * T_remaining_it)

#OPTION B)
#lambda is approx. = OAS/(1-RECOVERY_RATE), where RR is usually 0.4 as a standard level
OAS=ts_data['OAS_SPREAD_MID'].unstack('ticker')/10000
T_rem=(pd.to_datetime(static['MATURITY'])-prices.index[-1]).dt.days/365


S = np.exp(-OAS.divide(0.60)*T_rem)

#Preparring the partial effects (partial derivatives) of the d.p. with respect to the regressors  where Y is the delta log of the portfolio in between 2 moments in time (t and t-1)

D=ts_data['DUR_ADJ_MID'].unstack('ticker')
C=ts_data['CONVEXITY_MID'].unstack('ticker')
Z=ts_data['Z_SPREAD_MID'].unstack('ticker')/10000
CS=ts_data['OAS_SPREAD_MID'].unstack('ticker')/10000

panel= pd.DataFrame({
  'log_ret':log_delta_V_stack(),
  'D_M':D.stack(),
  'C':C.stack(),
  'Z':Z.stack(),
  'CS':CS.stack(),
  'S':S.stack()
}).dropna()

panel=panel.join(macro_ret,on='date')
panel['E__t']=1-np.exp(-0.0609*panel['D_M'])

#Mac-Beth FAMA factor model estimation:

from linearmodels.asset_pricing import LinearFactorModel
dates=panel.index.get_level_values('date').unique()
betas= []
for t in dates:
  cross= panel.xs(t,level='date')
  if len(cross)<10:
    continue
  x= cross[['D_M','C','Z','CS','S','E_t']].assign(const=1)
  y= cross['log_return']

  b= np-linalg.lstsq(X.values, y.values,rcond= None)[0]
  betas.append(dict(zip(X.columns,b))
betas_df=pd.DataFrame(betas.index=dates)
from statsmodels.stats.sandwich_covariance import cov_hac

beta_means= betas_df.mean()
for col in betas_df.columns:
  nw_var=cov_hac(betas_df[[col]].assign(const=1),nlags=5)
  print(f"{col}:{beta_means[col]:.4f},NW-SE:{np.sqrt(nw_var[0,0]/len(betas_df)):.4f}")



#2SLS for CS Endogeneity 

#Calculating the sector median to regress
from linearmodels.iv import IV2SLS
panel['CS_sector_loo']=(
  panel.groupby(['date','sector'])['CS'].transform(lambda x: (x.sum()-x)/(x.count()-1)  
)

for i in dates:
  cross = panel.xs(t,level='date')
  res=IV2SLS(
    dependent=cross['log_ret'],
    exog=cross['const','D_M','C','Z','S','E_t'],
    endog=cross['CS'],
    instruments= cross[['CS_sector_loo']]
  ).fit(cov_type='robust')



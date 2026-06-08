import numpy as np
import pandas as pd
from scipy.stats import norm, multivariate_normal

class CorrelatedEngine:
    def __init__(self, correlation_matrix: pd.DataFrame):
        self.corr_matrix = correlation_matrix
        self.num_vars = len(correlation_matrix)
        
    def simulate(self, marginals: list, n_sims: int = 1000):
        """
        marginals: list of callable cdf/ppf functions (e.g., scipy.stats.poisson/nbinom)
        """
        # 1. Generate correlated samples from multivariate normal (the copula)
        mvn = multivariate_normal(mean=np.zeros(self.num_vars), cov=self.corr_matrix)
        correlated_normals = mvn.rvs(size=n_sims)
        
        # 2. Map to Uniform(0, 1) using Gaussian CDF
        uniforms = norm.cdf(correlated_normals)
        
        # 3. Map to Target Distributions using Inverse CDF (PPF)
        results = np.zeros((n_sims, self.num_vars))
        for i in range(self.num_vars):
            results[:, i] = marginals[i].ppf(uniforms[:, i])
            
        return results

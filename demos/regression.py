# Copyright 2018 Hugh Salimbeni (hrs13@ic.ac.uk), Ching-An Cheng (cacheng@gatech.edu)
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from scipy.cluster.vq import kmeans2

from bayesian_benchmarks.tasks.regression import run as run_regression
import numpy as np

from gpflow.kernels import Matern52
from gpflow.likelihoods import Gaussian
from gpflow.training import NatGradOptimizer, AdamOptimizer

from odvgp.odvgp import ODVGP, DVGP


class SETTINGS:
    # model
    likelihood_variance = 1e-2
    lengthscales = 0.1

    # training
    iterations = 1000
    ng_stepsize = 5e-2
    adam_stepsize = 1e-3
    minibatch_size = 1024
    gamma_minibatch_size = 64


class DATASET_ARGS:
    dataset = 'protein'
    split = 0


class Model_ODVGP:
    """
    Bayesian_benchmarks-compatible wrapper around the orthogonally decoupled variational GP from 
    
    @inproceedings{salimbeni2018decoupled,
      title={Orthogonally Decoupled Variational Gaussian Processes},
      author={Salimbeni, Hugh and Cheng, Ching-An and Boots, Byron and Deisenroth, Marc},
      booktitle={Advances in Neural Information Processing Systems},
      year={2018}
    }
       
    The natural gradient step for the beta parameters can be implemented using standard 
    gpflow tools, due to the decoupling. We optimize the rest of the parameters using adam. 
    
    """
    def __init__(self, M_gamma, M_beta):
        self.M_gamma = M_gamma
        self.M_beta = M_beta
        self.model = None

    def init_model(self, Model, X, Y):
        Dx = X.shape[1]
        kern = Matern52(Dx, lengthscales=SETTINGS.lengthscales * Dx ** 0.5)
        lik = Gaussian()
        lik.variance = SETTINGS.likelihood_variance

        gamma = kmeans2(X, self.M_gamma, minit='points')[0] if self.M_gamma > 0 else np.empty((0, Dx))
        beta = kmeans2(X, self.M_beta, minit='points')[0]

        gamma_minibatch_size = SETTINGS.gamma_minibatch_size if self.M_gamma>0 else None

        self.model = Model(X, Y, kern, lik, gamma, beta,
                           minibatch_size=SETTINGS.minibatch_size,
                           gamma_minibatch_size=gamma_minibatch_size)
        self.sess = self.model.enquire_session()

    def fit(self, X, Y):
        if not self.model:
            self.init_model(ODVGP, X, Y)

        var_list = [[self.model.basis.a_beta, self.model.basis.L]]
        self.model.basis.a_beta.set_trainable(False)

        op_ng = NatGradOptimizer(SETTINGS.ng_stepsize).make_optimize_tensor(self.model, var_list=var_list)
        op_adam = AdamOptimizer(SETTINGS.adam_stepsize).make_optimize_tensor(self.model)
        for it in range(SETTINGS.iterations):
            self.sess.run(op_ng)
            self.sess.run(op_adam)

            if it % 100 == 0:
                print('{} {:.4f}'.format(it, self.sess.run(self.model.likelihood_tensor)))

        self.model.anchor(self.sess)

    def predict(self, Xs):
        return self.model.predict_y(Xs, session=self.sess)


class Model_DVGP(Model_ODVGP):
    """
    Wrapper around the decoupled variational GP, from 
    
    @inproceedings{cheng2017variational,
      title={Variational Inference for Gaussian Process Models with Linear Complexity},
      author={Cheng, Ching-An and Boots, Byron},
      booktitle={Advances in Neural Information Processing Systems},
      year={2017}
    }
    
    We don't have a natural gradient update here, so we optimize everything with adam.
    
    """
    def fit(self, X, Y):
        if not self.model:
            self.init_model(DVGP, X, Y)

        op_adam = AdamOptimizer(SETTINGS.adam_stepsize).make_optimize_tensor(self.model)
        for it in range(SETTINGS.iterations):
            self.sess.run(op_adam)

            if it % 100 == 0:
                print('{} {:.4f}'.format(it, self.sess.run(self.model.likelihood_tensor)))

        self.model.anchor(self.sess)


# small demos
res = run_regression(DATASET_ARGS, model=Model_ODVGP(500, 100), is_test=True)
print('orthogonally decoupled model test loglik {:.4f}'.format(res['test_loglik']))

res = run_regression(DATASET_ARGS, model=Model_ODVGP(0, 100), is_test=True)
print('vanilla coupled model test loglik {:.4f}'.format(res['test_loglik']))

res = run_regression(DATASET_ARGS, model=Model_DVGP(600, 100), is_test=True)
print('decoupled model test loglik {:.4f}'.format(res['test_loglik']))




"""Janggo - deep learning for genomics"""

import hashlib
import logging
import os
import time

import h5py
from keras import backend as K
from keras.models import Model
from keras.models import load_model

from janggo.utils import get_parse_tree
from janggo.layers import Complement
from janggo.layers import Reverse


class Janggo(object):
    """Janggo model

    The class :class:`Janggo` builds up on :class:`keras.models.Model`
    and allows to instantiate a neural network model.
    This class contains methods to fit, predict and evaluate the model.

    Parameters
    -----------
    inputs : Input or list(Input)
        Input layer or list of Inputs as defined by keras.
        See https://keras.io/layers.
    outputs : Layer or list(Layer)
        Output layer or list of outputs. See https://keras.io/layers.
    name : str
        Name of the model.
    outputdir : str
        Output folder in which the log-files and model parameters
        are stored. Default: 'janggo_results'.
    """
    timer = None
    _name = None

    def __init__(self, inputs, outputs, name,
                 outputdir=None):

        self.name = name
        self.kerasmodel = Model(inputs, outputs, name)

        if not outputdir:  # pragma: no cover
            # this is excluded from the unit tests for which
            # only temporary directories should be used.
            outputdir = os.path.join(os.path.expanduser("~"), 'janggo_results')
        self.outputdir = outputdir

        if not os.path.exists(outputdir):  # pragma: no cover
            # this is excluded from unit tests, because the testing
            # framework always provides a directory
            os.makedirs(outputdir)

        if not os.path.exists(os.path.join(outputdir, 'logs')):
            os.makedirs(os.path.join(outputdir, 'logs'))

        logfile = os.path.join(outputdir, 'logs', 'janggo.log')

        self.logger = logging.getLogger(self.name)

        logging.basicConfig(filename=logfile,
                            level=logging.DEBUG,
                            format='%(asctime)s:%(name)s:%(message)s',
                            datefmt='%m/%d/%Y %I:%M:%S')

        self.logger.info("Model Summary:")
        self.kerasmodel.summary(print_fn=self.logger.info)

    @classmethod
    def create_by_name(cls, name, outputdir=None):
        """Creates a Janggo object by name.

        This option is usually used to load an already trained model.

        Parameters
        ----------
        name : str
            Name of the model.
        outputdir : str
            Output directory. Default: '~/janggo_results/'.

        Examples
        --------
        .. code-block:: python

          from janggo import Janggo

          def test_model(inputs, inp, oup, params):
              in_ = Input(shape=(10,), name='ip')
              output = Dense(1, activation='sigmoid', name='out')(in_)
              return in_, output

          # create a now model
          model = Janggo.create(name='test_model', (test_model, None))
          model.save()

          # remove the original model
          del model

          # reload the model
          model = Janggo.create_by_name('test_model')
        """
        if not outputdir:  # pragma: no cover
            # this is excluded from the unit tests for which
            # only temporary directories should be used.
            outputdir = os.path.join(os.path.expanduser("~"), 'janggo_results')
        path = cls._storage_path(name, outputdir)

        model = load_model(path,
                           custom_objects={'Reverse': Reverse,
                                           'Complement': Complement})
        return cls(model.inputs, model.outputs, name, outputdir)

    @property
    def name(self):
        """Name property"""
        return self._name

    @name.setter
    def name(self, name):
        if not isinstance(name, str):
            raise Exception("Name must be a string.")
        if '.' in name:
            raise Exception("'.' in the name is not allowed.")
        self._name = name

    def save(self, filename=None, overwrite=True):
        """Saves the model.

        Parameters
        ----------
        filename : str
            Filename of the stored model. Default: None.
        overwrite: bool
            Overwrite a stored model. Default: False.
        """
        if not filename:  # pragma: no cover
            filename = self._storage_path(self.name, self.outputdir)

        self.logger.info("Save model %s", filename)
        self.kerasmodel.save(filename, overwrite)

    def summary(self):
        """Prints the model definition."""
        self.kerasmodel.summary()

    @classmethod
    def create(cls, modeldef, inputp=None, outputp=None, name=None,
               outputdir=None, modelzoo=None):
        """Instantiate a Janggo model.

        This method instantiates a Janggo model with a given name
        and model definition. This method can be used to automatically
        infer the input and output shapes for the model (see Examples).

        Parameters
        -----------
        modeldef : tuple
            Contains a function that defines a model template and
            additional model parameters.
        inputp : dict or None
            Dictionary containing dataset properties such as the input
            shapes. This argument can be determined using
            :func:`input_props` on the provided Input Datasets.
        outputp : dict or None
            Dictionary containing dataset properties such as the output
            shapes. This argument can be determined using
            :func:`output_props` on the provided training labels.
        name : str or None
            Model name. If None, a model name will be generated automatically.
            If a name is provided, it overwrites the automatically generated
            model name.
        outputdir : str or None
            Directory in which the log files, model parameters etc.
            will be stored.
        modelzoo : str or None
            Modelzoo defines the location of a python script that contains
            the model definitions. If a modelzoo is provided, it will be checked
            if the model definition has changed and a unique hash is generated
            accordingly. If None, the hash is created without taking the function
            definition into account.

        Examples
        --------
        Variant 1: Specify all layers manually

        .. code-block:: python

          from janggo import Janggo

          def test_manual_model(inputs, inp, oup, params):
              in_ = Input(shape=(10,), name='ip')
              output = Dense(1, activation='sigmoid', name='out')(in_)
              return in_, output

          model = Janggo.create(name='test_model', (test_manual_model, None))

        Variant 2: Automatically infer the input and output layers.
        This variant leaves only the network body to be specified.

        .. code-block:: python

          from numpy as np
          from janggo import Janggo
          from janggo import inputlayer, outputlayer
          from janggo.data import input_props, output_props
          from jangoo.data import NumpyDataset

          # Some random data
          DATA = NumpyDataset('ip', np.random.random((1000, 10)))
          LABELS = NumpyDataset('out', np.random.randint(2, size=(1000, 1)))

          # inputlayer and outputlayer automatically infer the layer shapes
          @inputlayer
          @outputlayer
          def test_inferred_model(inputs, inp, oup, params):
              in_ = output = inputs_['ip']
              return in_, output

          inp = input_props(DATA)
          oup = output_props(LABELS)
          model = Janggo.create(name='test_model', (test_inferred_model, None),
                                inputp=inp, outputp=oup)

          # Compile the model
          model.compile(optimizer='adadelta', loss='binary_crossentropy')
        """

        print('create model')
        modelfct = modeldef[0]
        modelparams = modeldef[1]

        K.clear_session()
        if not name:
            if modelzoo:
                parsetree = get_parse_tree(modelzoo)
                # get dict(modelname: def)
                name_ = str(parsetree[modelfct.__name__])
            else:
                name_ = modelfct.__name__

            name_ += str(modelparams)

            name_ = str(inputp) + str(outputp)
            hasher = hashlib.md5()
            hasher.update(name_.encode('utf-8'))
            name = hasher.hexdigest()
            print("Generated id: '{}' for {}".format(name, modelfct.__name__))


        inputs, outputs = modelfct(None, inputp, outputp, modelparams)

        model = cls(inputs=inputs, outputs=outputs, name=name,
                    outputdir=outputdir)

        return model

    def compile(self, optimizer, loss, metrics=None,
                loss_weights=None, sample_weight_mode=None,
                weighted_metrics=None, target_tensors=None):
        """Compiles a model.

        This method invokes keras.models.Model.compile
        (see https://keras.io/models/model/) in order to compile
        the keras model that Janggo maintains.

        The parameters are identical to the corresponding keras method.
        """

        self.kerasmodel.compile(optimizer, loss, metrics, loss_weights,
                                sample_weight_mode, weighted_metrics,
                                target_tensors)

    def fit(self,
            inputs=None,
            outputs=None,
            batch_size=None,
            epochs=1,
            verbose=1,
            callbacks=None,
            validation_split=0.,
            validation_data=None,
            shuffle=True,
            class_weight=None,
            sample_weight=None,
            initial_epoch=0,
            steps_per_epoch=None,
            validation_steps=None,
            generator=None,
            use_multiprocessing=True,
            workers=1,
            **kwargs):
        """Fit the model.

        This method is used to fit a given model.
        All of the parameters are directly delegated the keras model
        fit or fit_generator method.
        See https://keras.io/models/model/#methods.
        If a generator is supplied, the fit_generator method of the
        respective keras model will be invoked.
        Otherwise the fit method is used.

        Janggo provides a readily available generator.
        See :func:`janggo_fit_generator`.

        Generally, generators need to adhere to the following signature:
        `generator(inputs, outputs, batch_size, sample_weight=None,
        shuffle=False)`.

        Examples
        --------
        Variant 1: Use `fit` without a generator

        .. code-block:: python

          model.fit(DATA, LABELS)

        Variant 2: Use `fit` with a generator

        .. code-block:: python

          from janggo import janggo_fit_generator

          model.fit(DATA, LABELS, generator=janggo_fit_generator)
        """

        inputs = self.__convert_data(inputs)
        outputs = self.__convert_data(outputs)

        hyper_params = {
            'epochs': epochs,
            'batch_size': batch_size,
            'shuffle': shuffle,
            'class_weight': class_weight,
            'initial_epoch': initial_epoch,
            'steps_per_epoch': steps_per_epoch,
            'generator': True if generator else False,
            'use_multiprocessing': use_multiprocessing,
            'workers': workers
        }

        self.logger.info('Fit: %s', self.name)
        self.logger.info("Input:")
        self.__dim_logging(inputs)
        self.logger.info("Output:")
        self.__dim_logging(outputs)
        self.timer = time.time()
        history = None

        if generator:

            try:
                if not isinstance(inputs, (list, dict)):
                    raise TypeError("inputs must be a Dataset, "
                                    + "list(Dataset)"
                                    + "or dict(Dataset) if used with a "
                                    + "generator. Got {}".format(type(inputs)))
                if not batch_size:
                    batch_size = 32

                for k in inputs:
                    xlen = len(inputs[k])
                    break

                if not steps_per_epoch:
                    steps_per_epoch = xlen//batch_size + \
                        (1 if xlen % batch_size > 0 else 0)

                if validation_data:
                    if len(validation_data) == 2:
                        vgen = generator(validation_data[0],
                                         validation_data[1],
                                         batch_size,
                                         shuffle=shuffle)
                    else:
                        vgen = generator(validation_data[0],
                                         validation_data[1],
                                         batch_size,
                                         sample_weight=validation_data[2],
                                         shuffle=shuffle)

                    if not validation_steps:
                        validation_steps = len(validation_data[0])//batch_size + \
                                    (1 if len(validation_data[0]) % batch_size > 0
                                     else 0)
                else:
                    vgen = None

                history = self.kerasmodel.fit_generator(
                    generator(inputs, outputs, batch_size,
                              sample_weight=sample_weight,
                              shuffle=shuffle),
                    steps_per_epoch=steps_per_epoch,
                    epochs=epochs,
                    validation_data=vgen,
                    validation_steps=validation_steps,
                    class_weight=class_weight,
                    initial_epoch=initial_epoch,
                    shuffle=False,  # must be false!
                    use_multiprocessing=use_multiprocessing,
                    max_queue_size=50,
                    workers=workers,
                    verbose=verbose,
                    callbacks=callbacks)
            except Exception:  # pragma: no cover
                self.logger.exception('fit_generator failed:')
                raise
        else:
            try:
                history = self.kerasmodel.fit(inputs, outputs, batch_size, epochs,
                                              verbose,
                                              callbacks, validation_split,
                                              validation_data, shuffle,
                                              class_weight,
                                              sample_weight, initial_epoch,
                                              steps_per_epoch,
                                              validation_steps,
                                              **kwargs)
            except Exception:  # pragma: no cover
                self.logger.exception('fit failed:')
                raise

        self.logger.info('#' * 40)
        for k in history.history:
            self.logger.info('%s: %f', k, history.history[k][-1])
        self.logger.info('#' * 40)

        self.save()
        self._save_hyper(hyper_params)

        self.logger.info("Training finished after %1.3f s",
                         time.time() - self.timer)
        return history

    def predict(self, inputs,
                batch_size=None,
                verbose=0,
                steps=None,
                generator=None,
                use_multiprocessing=True,
                layername=None,
                workers=1):

        """Predict targets.

        This method predicts the targets.
        All of the parameters are directly delegated the keras model
        predict or predict_generator method.
        See https://keras.io/models/model/#methods.
        If a generator is supplied, the `predict_generator` method of the
        respective keras model will be invoked.
        Otherwise the `predict` method is used.

        Janggo provides a readily available generator for this method
        See :func:`janggo_predict_generator`.

        Generally, generators need to adhere to the following signature:
        `generator(inputs, batch_size, sample_weight=None, shuffle=False)`.

        Examples
        --------
        Variant 1: Use `predict` without a generator

        .. code-block:: python

          model.predict(DATA)

        Variant 2: Use `predict` with a generator

        .. code-block:: python

          from janggo import janggo_predict_generator

          model.predict(DATA, generator=janggo_predict_generator)
        """

        inputs = self.__convert_data(inputs)

        self.logger.info('Predict: %s', self.name)
        self.logger.info("Input:")
        self.__dim_logging(inputs)
        self.timer = time.time()

        # if a desired layername is specified, the features
        # will be predicted.
        if layername:
            model = Model(self.kerasmodel.input,
                          self.kerasmodel.get_layer(layername).output)
        else:
            model = self.kerasmodel

        if generator:
            if not isinstance(inputs, (list, dict)):
                raise TypeError("inputs must be a Dataset, list(Dataset)"
                                + "or dict(Dataset) if used with a "
                                + "generator.")
            if not batch_size:
                batch_size = 32

            for k in inputs:
                xlen = len(inputs[k])
                break

            if not steps:
                steps = xlen//batch_size + (1 if xlen % batch_size > 0 else 0)

            try:
                return model.predict_generator(
                    generator(inputs, batch_size),
                    steps=steps,
                    use_multiprocessing=use_multiprocessing,
                    workers=workers,
                    verbose=verbose)
            except Exception:  # pragma: no cover
                self.logger.exception('predict_generator failed:')
                raise
        else:
            try:
                return model.predict(inputs, batch_size, verbose, steps)
            except Exception:  # pragma: no cover
                self.logger.exception('predict failed:')
                raise

    def evaluate(self, inputs=None, outputs=None,
                 batch_size=None,
                 verbose=1,
                 sample_weight=None,
                 steps=None,
                 generator=None,
                 use_multiprocessing=True,
                 workers=1):
        """Evaluate the model performance.

        This method is used to evaluate a given model.
        All of the parameters are directly delegated the keras model
        `evaluate` or `evaluate_generator` method.
        See https://keras.io/models/model/#methods.
        If a generator is supplied, the `evaluate_generator` method of the
        respective keras model will be invoked.
        Otherwise the `evaluate` method is used.

        Janggo provides a readily available generator.
        See :func:`janggo_fit_generator`.

        Generally, generators need to adhere to the following signature:
        `generator(inputs, outputs, batch_size, sample_weight=None,
        shuffle=False)`.

        Examples
        --------
        Variant 1: Use `evaluate` without a generator

        .. code-block:: python

          model.evaluate(DATA, LABELS)

        Variant 2: Use `evaluate` with a generator

        .. code-block:: python

          from janggo import janggo_fit_generator

          model.evaluate(DATA, LABELS, generator=janggo_fit_generator)
        """

        inputs = self.__convert_data(inputs)
        outputs = self.__convert_data(outputs)

        self.logger.info('Evaluate: %s', self.name)
        self.logger.info("Input:")
        self.__dim_logging(inputs)
        self.logger.info("Output:")
        self.__dim_logging(outputs)
        self.timer = time.time()

        if generator:

            if not isinstance(inputs, (list, dict)):
                raise TypeError("inputs must be a Dataset, list(Dataset)"
                                + "or dict(Dataset) if used with a "
                                + "generator.")
            if not batch_size:
                batch_size = 32

            for k in inputs:
                xlen = len(inputs[k])
                break

            if not steps:
                steps = xlen//batch_size + (1 if xlen % batch_size > 0 else 0)

            try:
                values = self.kerasmodel.evaluate_generator(
                    generator(inputs, outputs, batch_size,
                              sample_weight=sample_weight,
                              shuffle=False),
                    steps=steps,
                    use_multiprocessing=use_multiprocessing,
                    workers=workers)
            except Exception:  # pragma: no cover
                self.logger.exception('evaluate_generator failed:')
                raise
        else:
            try:
                values = self.kerasmodel.evaluate(inputs, outputs, batch_size,
                                                  verbose,
                                                  sample_weight, steps)
            except Exception:  # pragma: no cover
                self.logger.exception('evaluate_generator failed:')
                raise

        self.logger.info('#' * 40)
        if not isinstance(values, list):
            values = [values]
        for i, value in enumerate(values):
            self.logger.info('%s: %f', self.kerasmodel.metrics_names[i], value)
        self.logger.info('#' * 40)

        self.logger.info("Evaluation finished in %1.3f s",
                         time.time() - self.timer)
        return values

    def __dim_logging(self, data):
        if isinstance(data, dict):
            for key in data:
                self.logger.info("\t%s: %s", key, data[key].shape)

        if hasattr(data, "shape"):
            data = [data]

        if isinstance(data, list):
            for datum in data:
                self.logger.info("\t%s", datum.shape)

    @staticmethod
    def __convert_data(data):
        # If we deal with Dataset, we convert it to a Dictionary
        # which is directly interpretable by keras
        if hasattr(data, "name") and hasattr(data, "shape"):
            c_data = {}
            c_data[data.name] = data
        elif isinstance(data, list) and \
                hasattr(data[0], "name") and hasattr(data[0], "shape"):
            c_data = {}
            for datum in data:
                c_data[datum.name] = datum
        else:
            # Otherwise, we deal with non-bwdatasets (e.g. numpy)
            # which for compatibility reasons we just pass through
            c_data = data
        return c_data

    @staticmethod
    def _storage_path(name, outputdir):
        """Returns the path to the model storage file."""
        if not os.path.exists(os.path.join(outputdir, "models")):
            os.mkdir(os.path.join(outputdir, "models"))
        filename = os.path.join(outputdir, 'models', '{}.h5'.format(name))
        return filename

    def _save_hyper(self, hyper_params, filename=None):
        """This method attaches the hyper parameters to an hdf5 file.

        This method is supposed to be used after model training.
        It attaches the hyper parameter, e.g. epochs, batch_size, etc.
        to the hdf5 file that contains the model weights.
        The hyper parameters are added as attributes to the
        group 'model_weights'

        Parameters
        ----------
        hyper_parameters : dict
            Dictionary that contains the hyper parameters.
        filename : str
            Filename of the hdf5 file. This file must already exist.
        """
        if not filename:  # pragma: no cover
            filename = self._storage_path(self.name, self.outputdir)

        content = h5py.File(filename, 'r+')
        weights = content['model_weights']
        for key in hyper_params:
            if hyper_params[key]:
                weights.attrs[key] = hyper_params[key]
        content.close()

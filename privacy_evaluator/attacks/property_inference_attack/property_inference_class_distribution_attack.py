from ...attacks.attack import Attack
from ...classifiers.classifier import Classifier
from ...utils import data_utils
from ...output.user_output_property_inference_attack import (
    UserOutputPropertyInferenceAttack,
)
from .property_inference_attack import PropertyInferenceAttack

import numpy as np
import logging
from tqdm.auto import tqdm
from typing import Tuple, Dict, List
from collections import OrderedDict


# count of shadow training sets, must be even
AMOUNT_SETS = 2
# ratio and size for unbalanced data sets
SIZE_SHADOW_TRAINING_SET = 1000
# ratios for different properties in sub-attacks
RATIOS_FOR_ATTACK = [
    0.05,
    0.1,
    0.15,
    0.2,
    0.25,
    0.3,
    0.35,
    0.4,
    0.45,
    0.55,
    0.6,
    0.65,
    0.7,
    0.75,
    0.8,
    0.85,
    0.9,
    0.95,
]
# classes the attack should be performed on
CLASSES = [0, 1]

# number of epochs for training the meta classifier
NUM_EPOCHS_META_CLASSIFIER = 20

# ratio of negation of property
NEGATIVE_RATIO = 0.5


class PropertyInferenceClassDistributionAttack(PropertyInferenceAttack):
    def __init__(
        self,
        target_model: Classifier,
        dataset: Tuple[np.ndarray, np.ndarray],
        amount_sets: int = AMOUNT_SETS,
        size_shadow_training_set: int = SIZE_SHADOW_TRAINING_SET,
        ratios_for_attack: List[int] = RATIOS_FOR_ATTACK,
        negative_ratio: int = NEGATIVE_RATIO,
        classes: List[int] = CLASSES,
        verbose: int = 0,
        num_epochs_meta_classifier: int = NUM_EPOCHS_META_CLASSIFIER,
    ):
        """
        Initialize the Property Inference Attack Class.
        :param target_model: the target model to be attacked
        :param dataset: dataset for training of shadow classifiers, test_data from dataset
        :param amount_sets: count of shadow training sets, must be even
        :param size_shadow_training_set: ratio and size for unbalanced data sets
        :param ratios_for_attack: ratios for different properties in sub-attacks
        :param negative_ratio: ratio of negation of property (where in the case of two classes the ratio is applied to
        the second class and (1-ratio) to the first one)
        :param classes: classes the attack should be performed on
        :param verbose: 0: no information; 1: backbone (most important) information; 2: utterly detailed information will be printed
        :param num_epochs_meta_classifier: number of epochs for training the meta classifier
        """

        self.negative_ratio = negative_ratio
        self.classes = classes
        if len(self.classes) != 2:
            raise ValueError("Currently attack only works with two classes.")
        for class_number in self.classes:
            if class_number not in dataset[1]:
                raise ValueError(f"Class {class_number} does not exist in dataset.")

        for i in classes:
            length_class = len((np.where(dataset[1] == i))[0])
            if length_class < size_shadow_training_set:
                size_shadow_training_set_old = size_shadow_training_set
                size_shadow_training_set = length_class
                warning_message = (
                    "Warning: Number of samples for class {} is {}. "
                    "This is smaller than the given size set ({}). "
                    "{} is now the new size set."
                ).format(
                    i,
                    length_class,
                    size_shadow_training_set_old,
                    size_shadow_training_set,
                )
                self.logger.warning(warning_message)

        super().__init__(
            target_model,
            dataset,
            amount_sets,
            size_shadow_training_set,
            ratios_for_attack,
            num_epochs_meta_classifier,
            verbose,
        )

    def create_shadow_training_sets(
        self, num_elements_per_class: Dict[int, int]
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Create the shadow training sets with given ratio.
        The function works for the specific binary case that the ratio is a fixed distribution
        specified in the input.
        :param num_elements_per_class: number of elements per class
        :return: shadow training sets for given ratio
        """

        training_sets = []

        # Creation of shadow training sets with the size dictionaries
        # amount_sets divided by 2 because amount_sets describes the total amount of shadow training sets.
        # In this function however only all shadow training sets of one type (follow property OR negation of property) are created, hence amount_sets / 2.
        self.logger.info("Creating shadow training sets")

        for _ in range(int(self.amount_sets / 2)):
            shadow_training_set = data_utils.new_dataset_from_size_dict(
                self.dataset, num_elements_per_class
            )
            training_sets.append(shadow_training_set)

        return training_sets

    def create_shadow_classifier_from_training_set(
        self, num_elements_per_classes: Dict[int, int]
    ) -> list:
        """
        Creates and trains shadow classifiers from shadow training sets with specific ratio (= for one subattack).
        Calls create_shadow_training_sets and train_shadow_classifiers.
        :param num_elements_per_classes: number of elements per class
        :return: list of shadow classifiers, accuracies for the classifiers
        """

        # create training sets
        shadow_training_sets = self.create_shadow_training_sets(
            num_elements_per_classes
        )

        # create classifiers with trained models based on given data set
        shadow_classifiers = self.train_shadow_classifiers(
            shadow_training_sets, num_elements_per_classes
        )
        return shadow_classifiers

    def output_attack(self, predictions_ratios) -> UserOutputPropertyInferenceAttack:
        """
        Determination of prediction with highest probability.
        :param predictions_ratios: Prediction values from meta-classifier for different subattacks (different properties)
        :type predictions_ratios: OrderedDict[float, np.ndarray]
        :return: Output message for the attack
        """

        # get key & value of ratio with highest property probability
        max_property = max(predictions_ratios.items(), key=lambda item: item[1][0][0])

        output = dict()
        # rounding because calculation creates values like 0.499999999 when we expected 0.5
        for ratio in predictions_ratios:
            key = "class {}: {}, class {}: {}".format(
                self.classes[0], round(1 - ratio, 5), self.classes[1], round(ratio, 5)
            )
            output[key] = predictions_ratios[ratio][0][0]

        if len(self.ratios_for_attack) >= 2:
            max_message = (
                "The most probable property is class {}: {}, "
                "class {}: {} with a probability of {}.".format(
                    self.classes[0],
                    round(1 - max_property[0], 5),
                    self.classes[1],
                    round(max_property[0], 5),
                    predictions_ratios[max_property[0]][0][0],
                )
            )
        else:
            if list(predictions_ratios.values())[0][0][0] > 0.5:
                max_message = "The given distribution is more likely than a balanced distribution. " "The given distribution is class {}: {}, class {}: {}".format(
                    self.classes[0],
                    round(1 - self.ratios_for_attack[0], 5),
                    self.classes[1],
                    round(self.ratios_for_attack[0], 5),
                )
            else:
                max_message = "A balanced distribution is more likely than the given distribution. " "The given distribution is class {}: {}, class {}: {}".format(
                    self.classes[0],
                    round(1 - self.ratios_for_attack[0], 5),
                    self.classes[1],
                    round(self.ratios_for_attack[0], 5),
                )
            if abs(list(predictions_ratios.values())[0][0][0] - 0.5) <= 0.05:
                self.logger.warning(
                    "The probabilities are very close to each other. The prediction is likely to be a random guess."
                )

        return UserOutputPropertyInferenceAttack(max_message, output)

    def prediction_on_specific_property(
        self,
        feature_extraction_target_model: np.ndarray,
        shadow_classifiers_neg_property: list,
        ratio: float,
    ) -> np.ndarray:
        """
        Perform prediction for a subattack (specific property)
        :param feature_extraction_target_model: extracted features of target model
        :param shadow_classifiers_neg_property: balanced (= negation of property) shadow classifiers
        :param ratio: distribution for the property
        :return: Prediction of meta-classifier for property and negation property
        """

        # property of given ratio, only two classes allowed right now
        property_num_elements_per_classes = {
            self.classes[0]: int((1 - ratio) * self.size_shadow_training_set),
            self.classes[1]: int(ratio * self.size_shadow_training_set),
        }

        # create shadow classifiers with trained models with unbalanced data set
        shadow_classifiers_property = self.create_shadow_classifier_from_training_set(
            property_num_elements_per_classes
        )

        # create meta training set
        meta_features, meta_labels = self.create_meta_training_set(
            shadow_classifiers_property, shadow_classifiers_neg_property
        )

        # create meta classifier
        meta_classifier = self.train_meta_classifier(meta_features, meta_labels)

        # get prediction
        prediction = self.perform_prediction(
            meta_classifier, feature_extraction_target_model
        )

        return prediction

    def attack(self) -> UserOutputPropertyInferenceAttack:
        """
        Perform Property Inference attack.
        :return: message with most probable property, dictionary with all properties
        """
        self.logger.info("Initiating Property Inference Attack ... ")
        self.logger.info("Extracting features from target model ... ")
        # extract features of target model
        feature_extraction_target_model = self.feature_extraction(self.target_model)

        self.logger.info(
            "{} --- features extracted from the target model.".format(
                feature_extraction_target_model.shape
            )
        )

        # balanced ratio
        num_elements = int(round(self.size_shadow_training_set / len(self.classes)))

        # negation of property of given ratio, only two classes allowed right now
        neg_property_num_elements_per_class = {
            self.classes[0]: int(
                (1 - self.negative_ratio) * self.size_shadow_training_set
            ),
            self.classes[1]: int(self.negative_ratio * self.size_shadow_training_set),
        }

        self.logger.info(
            "Creating set of {} balanced shadow classifier(s) ... ".format(
                int(self.amount_sets / 2)
            )
        )
        # create balanced shadow classifiers negation property
        shadow_classifiers_neg_property = (
            self.create_shadow_classifier_from_training_set(
                neg_property_num_elements_per_class
            )
        )

        self.ratios_for_attack.sort()
        predictions = OrderedDict.fromkeys(self.ratios_for_attack, 0)
        # iterate over unbalanced ratios in 0.05 steps (0.05-0.45, 0.55-0.95)
        # (e.g. 0.55 means: class 0: 0.45 of all samples, class 1: 0.55 of all samples)

        self.logger.info(
            f"Performing PIA for the following ratios: {self.ratios_for_attack}."
        )

        for ratio in tqdm(
            self.ratios_for_attack,
            disable=(self.logger.level > logging.INFO),
            desc=f"Performing {len(self.ratios_for_attack)} sub-attack(s)",
        ):
            self.logger.info(f"Sub-attack for ratio {ratio} ... ")
            predictions[ratio] = self.prediction_on_specific_property(
                feature_extraction_target_model, shadow_classifiers_neg_property, ratio
            )
        self.logger.info("PIA completed!")
        return self.output_attack(predictions)

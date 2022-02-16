#!/bin/bash

# Usage: eval_model.sh <model> <iteration>

iter_arg=""


if [ $# -gt 1 ]; then
    iter_arg="--iteration $2"
fi

#eval_tasks="lambada piqa hellaswag winogrande mathqa pubmedqa wikitext pile_enron blimp_adjunct_island blimp_anaphor_gender_agreement blimp_anaphor_number_agreement blimp_animate_subject_passive blimp_animate_subject_trans blimp_causative blimp_complex_NP_island blimp_coordinate_structure_constraint_complex_left_branch blimp_coordinate_structure_constraint_object_extraction blimp_determiner_noun_agreement_1 blimp_determiner_noun_agreement_2 blimp_determiner_noun_agreement_irregular_1 blimp_determiner_noun_agreement_irregular_2 blimp_determiner_noun_agreement_with_adj_2 blimp_determiner_noun_agreement_with_adj_irregular_1 blimp_determiner_noun_agreement_with_adj_irregular_2 blimp_determiner_noun_agreement_with_adjective_1 blimp_distractor_agreement_relational_noun blimp_distractor_agreement_relative_clause blimp_drop_argument blimp_ellipsis_n_bar_1 blimp_ellipsis_n_bar_2 blimp_existential_there_object_raising blimp_existential_there_quantifiers_1 blimp_existential_there_quantifiers_2 blimp_existential_there_subject_raising blimp_expletive_it_object_raising blimp_inchoative blimp_intransitive blimp_irregular_past_participle_adjectives blimp_irregular_past_participle_verbs blimp_irregular_plural_subject_verb_agreement_1 blimp_irregular_plural_subject_verb_agreement_2 blimp_left_branch_island_echo_question blimp_left_branch_island_simple_question blimp_matrix_question_npi_licensor_present blimp_npi_present_1 blimp_npi_present_2 blimp_only_npi_licensor_present blimp_only_npi_scope blimp_passive_1 blimp_passive_2 blimp_principle_A_c_command blimp_principle_A_case_1 blimp_principle_A_case_2 blimp_principle_A_domain_1 blimp_principle_A_domain_2 blimp_principle_A_domain_3 blimp_principle_A_reconstruction blimp_regular_plural_subject_verb_agreement_1 blimp_regular_plural_subject_verb_agreement_2 blimp_sentential_negation_npi_licensor_present blimp_sentential_negation_npi_scope blimp_sentential_subject_island blimp_superlative_quantifiers_1 blimp_superlative_quantifiers_2 blimp_tough_vs_raising_1 blimp_tough_vs_raising_2 blimp_transitive blimp_wh_island blimp_wh_questions_object_gap blimp_wh_questions_subject_gap blimp_wh_questions_subject_gap_long_distance blimp_wh_vs_that_no_gap blimp_wh_vs_that_no_gap_long_distance blimp_wh_vs_that_with_gap blimp_wh_vs_that_with_gap_long_distance"
#eval_tasks="lambada piqa hellaswag winogrande mathqa pubmedqa wikitext"
eval_tasks="lambada piqa hellaswag winogrande mathqa wikitext pile_enron"

model=/mnt/ssd-1/igor/gpt-neox/models/$1
res_prefix=/mnt/ssd-1/igor/gpt-neox/results/$1

if [ $# -gt 1 ]; then
    res_prefix="$res_prefix.global_step$2"
fi

./deepy.py evaluate.py -d "$model/configs" config.yml --eval_results_prefix "$res_prefix" $iter_arg --eval_tasks $eval_tasks

import numpy as np
import pandas as pd
import random
import time
from ortools.graph import pywrapgraph
from cytospace.common import normalize_data, matrix_correlation_pearson, matrix_correlation_spearman, matrix_cosine
from scipy.spatial import distance


def import_solver(solver_method):
    try:
        if solver_method == "lapjv_compat":
            from lap import lapjv
            solver = lapjv
        elif solver_method == "lapjv":
            from lapjv import lapjv
            solver = lapjv
        else:
            raise NotImplementedError(f"The solver {solver_method} is not a supported solver "
                                      "for the shortest augmenting path method, choose between "
                                      "'lapjv' and 'lapjv_compat'.")
    except ModuleNotFoundError:
        raise ModuleNotFoundError("The Python package containing the solver_method option "
                                  f"you have chosen {solver_method} was not found. If you "
                                  "selected 'lapjv_compat' solver, install package 'lap'"
                                  "by running 'pip install lap==0.4.0'. If you selected 'lapjv'"
                                  "solver, install package 'lapjv' by running `pip intall lapjv==1.3.14'"
                                  "or check the package home page for further instructions.")

    return solver


def call_solver(solver, solver_method, cost_scaled):
    if solver_method == "lapjv_compat":
        _, _, y = solver(cost_scaled)
    elif solver_method == "lapjv":
        _, y, _ = solver(cost_scaled)

    return y

def calculate_cost(expressions_scRNA_data, expressions_st_data, cell_type_labels, cell_type_numbers_int,
                   cell_number_to_node_assignment, seed, solver_method, sampling_method, distance_metric):
    print("Down/up sample of scRNA-seq data according to estimated cell type fractions")
    t0 = time.perf_counter()
    # Find intersection genes
    intersect_genes = expressions_st_data.index.intersection(expressions_scRNA_data.index)
    original_cell_names = expressions_scRNA_data.columns
    expressions_scRNA_data_intersect_genes = expressions_scRNA_data.loc[intersect_genes, :]
    expressions_st_data_intersect_genes = expressions_st_data.loc[intersect_genes, :]
    expressions_scRNA = expressions_scRNA_data_intersect_genes.values.astype(float)
    expressions_st = expressions_st_data_intersect_genes.values.astype(float)

    # Data normalization
    expressions_tpm_st_log = normalize_data(expressions_st)
    expressions_tpm_scRNA_log = normalize_data(expressions_scRNA)

    # Down/up sample of scRNA-seq data according to estimated cell type fractions
    unique_cell_type_labels = sorted(np.unique(cell_type_labels.values[:,0]), key=str.lower)
    number_classes = len(unique_cell_type_labels)
    new_cell_type = np.zeros(number_classes + 1)

    # Build cost matrix
    np.random.seed(seed)
    random.seed(seed)
    sampled_index_total = []
    cell_names = []
    if sampling_method == "place_holders":
        for k in range(0, number_classes):
            cell_type_index = np.nonzero(cell_type_labels.values == unique_cell_type_labels[k])[0].tolist()
            fractions_cells = len(cell_type_index)
            fractions_beads = int(cell_type_numbers_int[k])
            if fractions_beads > fractions_cells:
               sampled_index = np.random.choice(cell_type_index,
                                                 fractions_beads - fractions_cells).tolist()
               exp_mat = expressions_scRNA[:,cell_type_index]
               num_genes = np.shape(expressions_scRNA)[0]
               num_cells = fractions_beads-fractions_cells
               b = np.zeros((num_genes,num_cells)) 
               for i1 in range(num_cells):
                   b[:,i1] = [np.random.choice(exp_mat[j1,:]) for j1 in range(num_genes)]
               cell_names = np.concatenate((cell_names,np.array(original_cell_names[cell_type_index])),axis=0)
               cell_names = np.concatenate((cell_names,np.array([unique_cell_type_labels[k]+'_new_'+str(i+1) for i in range(fractions_beads-fractions_cells)])),axis=0)
               b = (10**6) * (b/np.sum(b, axis = 0, dtype = float))
               b = np.log2(b + 1)
               new_cells = np.concatenate((expressions_tpm_scRNA_log[:,cell_type_index], b), axis = 1)
               all_new_cells_save = np.concatenate((expressions_scRNA[:,cell_type_index], b), axis = 1)
               sampled_index_total += cell_type_index + sampled_index                
            else:
               sampled_index = random.sample(cell_type_index, fractions_beads)
               new_cells = expressions_tpm_scRNA_log[:,sampled_index]
               all_new_cells_save = expressions_scRNA[:,sampled_index]
               cell_names = np.concatenate((cell_names,np.array(original_cell_names[sampled_index])),axis=0)
               sampled_index_total += sampled_index
               
            if k == 0:
                sampled_cells = new_cells
                all_cells_save = all_new_cells_save
                cell_types = np.array([unique_cell_type_labels[k]]*np.shape(new_cells)[1])

            else:
                sampled_cells = np.concatenate((sampled_cells, new_cells), axis=1)
                all_cells_save = np.concatenate((all_cells_save, all_new_cells_save), axis=1)
                cell_types = np.concatenate((cell_types,np.array([unique_cell_type_labels[k]]*np.shape(new_cells)[1])),axis=0)

        cell_ids_new = cell_names
    else:
                       
        for k in range(0, number_classes):
            cell_type_index = np.nonzero(cell_type_labels.values == unique_cell_type_labels[k])[0].tolist()
            fractions_cells = len(cell_type_index)
            fractions_beads = int(cell_type_numbers_int[k])
            if fractions_beads > fractions_cells:
                sampled_index = np.random.choice(cell_type_index,
                                                 fractions_beads - fractions_cells).tolist()
                new_cells = np.concatenate((expressions_tpm_scRNA_log[:, cell_type_index],
                                            expressions_tpm_scRNA_log[:, sampled_index]), axis=1)
                all_new_cells_save = np.concatenate((expressions_scRNA[:,cell_type_index], expressions_scRNA[:,sampled_index]), axis = 1)
                sampled_index_total += cell_type_index + sampled_index
            else:
                sampled_index = random.sample(cell_type_index, fractions_beads)
                new_cells = expressions_tpm_scRNA_log[:, sampled_index]
                all_new_cells_save = expressions_scRNA[:,sampled_index]
                sampled_index_total += sampled_index

            if k == 0:
                sampled_cells = new_cells
                all_cells_save = all_new_cells_save
            else:
                sampled_cells = np.concatenate((sampled_cells, new_cells), axis=1)
                all_cells_save = np.concatenate((all_cells_save, all_new_cells_save), axis=1)

        cell_ids = expressions_scRNA_data.columns.values
        cell_ids_new = cell_ids[sampled_index_total]
    
    new_cell_type[k + 1] = new_cell_type[k] + new_cells.shape[1]
    cell_ids = expressions_scRNA_data.columns.values
    cell_ids_selected = cell_ids[sampled_index_total]
    
    all_cells_save = pd.DataFrame(all_cells_save,dtype=int)
    all_cells_save.index = intersect_genes
    all_cells_save.columns = cell_ids_new

    print(f"Time to down/up sample scRNA-seq data: {round(time.perf_counter() - t0, 2)} seconds")

    print("Building cost matrix ...")
    t0 = time.perf_counter()
    if solver_method=="lap_CSPR":
        if distance_metric=="Pearson_correlation":
           cost = -np.transpose(matrix_correlation_pearson(expressions_tpm_st_log, sampled_cells))
        elif distance_metric=="Spearman_correlation":
           cost = -np.transpose(matrix_correlation_spearman(expressions_tpm_st_log, sampled_cells))
        elif distance_metric=="Cosine":
           cost = -np.transpose(matrix_cosine(expressions_tpm_st_log, sampled_cells))
        elif distance_metric=="Euclidean":
           cost = np.transpose(distance.cdist(np.transpose(sampled_cells), np.transpose(expressions_tpm_st_log), 'euclidean'))
    else:
        if distance_metric=="Pearson_correlation":
           cost = -matrix_correlation_pearson(sampled_cells, expressions_tpm_st_log)
        elif distance_metric=="Spearman_correlation":
           cost = -matrix_correlation_spearman(sampled_cells, expressions_tpm_st_log)
        elif distance_metric=="Cosine":
           cost = -matrix_cosine(sampled_cells, expressions_tpm_st_log)
        elif distance_metric=="Euclidean":
           cost = np.transpose(distance.cdist(np.transpose(sampled_cells), np.transpose(expressions_tpm_st_log), 'euclidean'))

    location_repeat = np.zeros(cost.shape[1])
    counter = 0
    for value, repeat in enumerate(cell_number_to_node_assignment):
        location_repeat[counter: counter + repeat] = value
        counter += repeat

    location_repeat = location_repeat.astype(int)
    distance_repeat = cost[location_repeat, :]
    print(f"Time to build cost matrix: {round(time.perf_counter() - t0, 2)} seconds")

    return distance_repeat, location_repeat, cell_ids_selected, new_cell_type, cell_ids_new, all_cells_save


def match_solution(cost):
    rows = len(cost)
    cols = len(cost[0])
    assignment_mat = np.zeros((rows, 2))
    assignment = pywrapgraph.LinearSumAssignment()
    for worker in range(rows):
        for task in range(cols):
            if cost[worker][task]:
                assignment.AddArcWithCost(worker, task, cost[worker][task])

    solve_status = assignment.Solve()
    if solve_status == assignment.OPTIMAL:
        print('Total cost = ', assignment.OptimalCost())
        print()
        for i in range(0, assignment.NumNodes()):
            assignment_mat[i, 0] = assignment.RightMate(i)
            assignment_mat[i, 1] = assignment.AssignmentCost(i)
    elif solve_status == assignment.INFEASIBLE:
        print('No assignment is possible.')
    elif solve_status == assignment.POSSIBLE_OVERFLOW:
        print('Some input costs are too large and may cause an integer overflow.')
    else:
        raise ValueError("The assignment failed")

    return assignment_mat

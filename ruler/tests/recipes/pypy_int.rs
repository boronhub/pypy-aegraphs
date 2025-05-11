use ruler::{
    enumo::{Filter, Metric, Ruleset, Workload},
    recipe_utils::{recursive_rules, run_workload, Lang},
    Limits,
};

use crate::Pred;

pub fn pypy_rules() -> Ruleset<Pred> {
    let mut all_rules = Ruleset::default();
    let bool_only = recursive_rules(
        Metric::Atoms,
        5,
        Lang::new(&["0", "1"], &["a", "b", "c"], &[&["int_not"], &["int_and", "int_or", "int_xor"]]),
        all_rules.clone(),
    );
    all_rules.extend(bool_only);
    let rat_only = recursive_rules(
        Metric::Atoms,
        5,
        Lang::new(
            &["-1", "0", "1"],
            &["a", "b", "c"],
            //&[&["int_neg", "int_abs"], &["int_add", "int_sub", "int_mul", "int_min", "int_max"]],
            &[&["int_neg"], &["int_add", "int_sub", "int_mul"]],
        ),
        all_rules.clone(),
    );
    all_rules.extend(rat_only.clone());
    let pred_only = recursive_rules(
        Metric::Atoms,
        5,
        Lang::new(
            &["-1", "0", "1"],
            &["a", "b", "c"],
            //&[&["int_neg", "int_abs"], &["int_le", "int_le", "int_eq", "int_neq"], &[]],
            &[&["int_neg"], &["int_le", "int_le", "int_eq", "int_ne"], &[]],
        ),
        all_rules.clone(),
    );
    all_rules.extend(pred_only);

    let full = recursive_rules(
        Metric::Atoms,
        5,
        Lang::new(
            &["-1", "0", "1"],
            &["a", "b", "c"],
            &[
                &["int_neg", "int_not"],
                &[
                    "int_and", "int_or", "int_xor", "int_add", "int_sub", "int_mul", "int_le", "int_le", "int_eq", "int_ne",
                ],
                &[],
            ],
        ),
        all_rules.clone(),
    );
    all_rules.extend(full);

    let nested_bops_arith = Workload::new(&["(bop e e)", "v"])
        .plug("e", &Workload::new(&["(bop v v)", "(uop v)", "v"]))
        .plug("bop", &Workload::new(&["int_add", "int_sub", "int_mul", "int_le"]))
        .plug("uop", &Workload::new(&["int_neg", "int_not"]))
        .plug("v", &Workload::new(&["a", "b", "c"]))
        .filter(Filter::Canon(vec![
            "a".to_string(),
            "b".to_string(),
            "c".to_string(),
        ]));
    let new = run_workload(
        nested_bops_arith,
        all_rules.clone(),
        Limits::synthesis(),
        Limits::minimize(),
        true,
    );
    all_rules.extend(new);
    let nested_bops_full = Workload::new(&["(bop e e)", "v"])
        .plug("e", &Workload::new(&["(bop v v)", "(uop v)", "v"]))
        .plug(
            "bop",
            &Workload::new(&["int_and", "int_or", "int_ne", "int_le", "int_eq", "int_le"]),
        )
        .plug("uop", &Workload::new(&["int_neg", "int_not"]))
        .plug("v", &Workload::new(&["a", "b", "c"]))
        .filter(Filter::Canon(vec![
            "a".to_string(),
            "b".to_string(),
            "c".to_string(),
        ]));
    let new = run_workload(
        nested_bops_full,
        all_rules.clone(),
        Limits::synthesis(),
        Limits::minimize(),
        true,
    );
    all_rules.extend(new.clone());

    // NOTE: The following workloads do NOT use all_rules as prior rules
    // Using all_rules as prior_rules leads to OOM
    /* let select_base = Workload::new([
        "(select V V V)",
        "(select V (OP V V) V)",
        "(select V V (OP V V))",
        "(select V (OP V V) (OP V V))",
        "(OP V (select V V V))",
    ])
    .plug("V", &Workload::new(["a", "b", "c", "d"]));

    let arith = select_base
        .clone()
        .plug("OP", &Workload::new(["int_add", "int_sub", "int_mul"]));
    let new = run_workload(
        arith,
        rat_only.clone(),
        Limits::synthesis(),
        Limits {
            iter: 1,
            node: 100_000,
            match_: 100_000,
        },
        true,
    );
    all_rules.extend(new);

    let arith = select_base.plug("OP", &Workload::new(["int_min", "int_max"]));
    let new = run_workload(
        arith,
        rat_only.clone(),
        Limits::synthesis(),
        Limits {
            iter: 1,
            node: 100_000,
            match_: 100_000,
        },
        true,
    );
    all_rules.extend(new); */

    all_rules
}
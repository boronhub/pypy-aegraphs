def lift_rule(s_expression: str) -> str:
    s_expression = s_expression.strip()
    bi_dir = False
    if "<=>" in s_expression:
        lhs, rhs = s_expression.split("<=>")
        bi_dir = True
    elif "==>" in s_expression:
        lhs, rhs = s_expression.split("==>")
    else:
        raise ValueError("Invalid rule format. Expected '<=>' or '==>'")
    rule_name = "_"
    operators_and_consts = []

    def parse_expression(expr):
        if expr.startswith("(") and expr.endswith(")"):
            expr = expr[1:-1].strip()
            parts = []
            depth = 0
            current = []
            for char in expr:
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                if char == " " and depth == 0:
                    parts.append("".join(current).strip())
                    current = []
                else:
                    current.append(char)
            if current:
                parts.append("".join(current).strip())
            operator = parts[0]
            operators_and_consts.append(operator)
            arguments = ", ".join(parse_expression(arg) for arg in parts[1:])
            return f"{operator}({arguments})"
        else:
            if expr.isdigit():
                operators_and_consts.append(expr)
            return expr.replace("?", "")

    lhs_parsed = parse_expression(lhs.strip())
    rhs_parsed = parse_expression(rhs.strip())
    name = "_".join(operators_and_consts)
    if bi_dir:
        rule = f"{name} : {lhs_parsed} \n=> {rhs_parsed}\n{name} : {rhs_parsed} => {lhs_parsed}"
    else:
        rule = f"{name} : {lhs_parsed} \n=> {rhs_parsed}"
    return rule


""" s_expression = "(int_sub 1 (int_or ?b ?a)) <=> (int_not (int_or ?b ?a))"
result = lift_rule(s_expression)
print(result)
 """
try:
    with open("gen_pypy_int_rules_a5.rules", "r") as source_file, open(
        "real.rules", "w"
    ) as destination_file:
        for line in source_file:
            destination_file.write(lift_rule(line))
            destination_file.write("\n\n\n")
except FileNotFoundError:
    print("The source file was not found.")

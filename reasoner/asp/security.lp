% Security Operations - Incident Triage Knowledge Base
% LiveLogic ASP Reasoning Engine

% === DSPy-populated facts ===
% user(U). resource(R). action(A). ip(I). role(Rl).
% user(john). has_role(john, analyst). access_event(john, db_server, read, "192.168.1.50", t1).
% policy_rule(r42, deny, db_server, read, "192.168.1.0/24").

% === Derived predicates ===

has_role(U, Rl) :- user(U), assigned_role(U, Rl).

permitted(U, R, A) :- has_role(U, Rl), allowed_role(Rl, R, A).

forbidden_ip_access(U, R, A) :- 
    access_event(U, R, A, IP, _), 
    forbidden_subnet(S), 
    ip_in_subnet(IP, S).

violation(policy, U, R, A, "insufficient_role") :- 
    access_event(U, R, A, _, _), not permitted(U, R, A).

violation(network, U, R, A, "forbidden_subnet") :- 
    forbidden_ip_access(U, R, A).

contradiction :- assigned_role(U, R1), assigned_role(U, R2), R1 != R2, user(U).

contradiction :- policy_rule(P1, allow, R, A, _), policy_rule(P2, deny, R, A, _), P1 != P2.

% === Meta-reasoning ===

missing_info("User Role") :- access_event(U, _, _, _, _), not has_role(U, _).

potential_fix(U, Role) :- missing_info("User Role"), suggested_role(U, Role).

% === Output directives ===

#show violation/5.
#show contradiction.
#show permitted/3.
#show missing_info/1.
#show potential_fix/2.

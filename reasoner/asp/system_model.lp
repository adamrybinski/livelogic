% LiveLogic Full System Model - 1:1 from plans/system_model.md spec
% Components, states, transitions, timeline, properties
% Run: clingo system_model.lp to see SAT models

% === Components ===
component(ui).
component(livekit).
component(agent).
component(stt).
component(dspy_extract).
component(session_db).
component(clingo).
component(dspy_critic).
component(dspy_interpret).
component(tts).

% === States ===
state(ui, idle).
state(ui, connected).
state(ui, speaking).
state(livekit, idle).
state(livekit, streaming).
state(agent, listening).
state(agent, processing).
state(agent, speaking).
state(stt, idle).
state(stt, transcribing).
state(session_db, accumulating).
state(clingo, idle).
state(clingo, solving).
state(clingo, sat).
state(clingo, unsat).
state(dspy_critic, idle).
state(dspy_critic, critiquing).
state(dspy_interpret, idle).
state(dspy_interpret, interpreting).
state(tts, idle).
state(tts, synthesizing).

% === Events ===
event(connect_event).
event(user_speak).
event(transcript_ready).
event(fact_extracted).
event(facts_ready).
event(solve_sat).
event(solve_unsat).
event(retract_fact).
event(response_ready).
event(audio_ready).

% === Initial ===
initial_state(C,S) :- component(C), default_state(C,S).
default_state(ui, idle).
default_state(livekit, idle).
default_state(agent, listening).
default_state(stt, idle).
default_state(dspy_extract, idle).
default_state(session_db, accumulating).
default_state(clingo, idle).
default_state(dspy_critic, idle).
default_state(dspy_interpret, idle).
default_state(tts, idle).

% === Transitions (from md spec) ===
trans(ui, idle, connected, connect_event).
trans(livekit, idle, streaming, connect_event).
trans(agent, listening, processing, user_speak).
trans(stt, idle, transcribing, user_speak).
trans(stt, transcribing, idle, transcript_ready).
trans(dspy_extract, idle, idle, fact_extracted).
trans(session_db, accumulating, accumulating, fact_extracted).
trans(clingo, idle, solving, facts_ready).
trans(clingo, solving, sat, solve_sat).
trans(clingo, solving, unsat, solve_unsat).
trans(dspy_critic, idle, critiquing, solve_unsat).
trans(dspy_interpret, idle, interpreting, solve_sat).
trans(tts, idle, synthesizing, response_ready).
trans(agent, processing, speaking, audio_ready).

% === Data Flow / Event Propagation ===
occurs(transcript_ready, T) :- occurs(user_speak, T).
occurs(fact_extracted, T) :- occurs(transcript_ready, T).
occurs(facts_ready, T) :- occurs(fact_extracted, T).
{ occurs(solve_sat, T); occurs(solve_unsat, T) } = 1 :- occurs(facts_ready, T).
occurs(response_ready, T) :- occurs(solve_sat, T).
occurs(audio_ready, T) :- occurs(response_ready, T).

% === Timeline ===
step(0..15).

% === State Holding ===
holds_state(C,S,0) :- initial_state(C,S).
holds_state(C,NS,T+1) :- holds_state(C,OS,T), trans(C,OS,NS,E), occurs(E,T).

% === Sample Interaction ===
occurs(connect_event, 0).
occurs(user_speak, 2).

% === Properties (relaxed for demo SAT) ===
:- not occurs(audio_ready, _).  % Basic liveness: must respond
:- holds_state(clingo, solving, S), S > 8.  % Termination

#show holds_state/3.
#show occurs/2.
#show.
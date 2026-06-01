// Test SVA file for navisv SVA Parser tests
// Contains various SVA assertion types: assert/assume/cover/restrict
// Plus disable iff, clocking, properties, sequences, etc.

module test_module (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  data,
    input  logic        valid,
    input  logic        ready,
    input  logic        enable,
    output logic        ack,
    output logic        err
);

    // Internal state
    logic [3:0] state;
    logic [7:0] count;
    logic [7:0] buffer;

    // Clocking default
    default clocking cb @(posedge clk);
        output state, count, buffer, ack, err;
        input data, valid, ready, enable;
    endclocking

    // ============================================
    // 1. assert - basic property
    // ============================================
    assert property (@(posedge clk) disable iff (!rst_n)
        valid |-> ##1 ack);

    assert property (@(posedge clk) disable iff (!rst_n)
        ready && valid |-> ##2 count == 8'h02);

    // ============================================
    // 2. assert - with sequence
    // ============================================
    sequence req_ack_seq;
        valid ##1 ready;
    endsequence

    assert property (@(posedge clk) disable iff (!rst_n)
        req_ack_seq |-> ##1 ack);

    // ============================================
    // 3. assume
    // ============================================
    assume property (@(posedge clk) disable iff (!rst_n)
        !rst_n || (state == 4'h0));

    // ============================================
    // 4. cover
    // ============================================
    cover property (@(posedge clk) disable iff (!rst_n)
        valid ##1 ready ##1 ack);

    // ============================================
    // 5. restrict
    // ============================================
    restrict property (@(posedge clk) disable iff (!rst_n)
        !enable || (count < 8'd16));

    // ============================================
    // 6. property definition
    // ============================================
    property p_valid_handshake;
        @(posedge clk) disable iff (!rst_n)
        valid |-> ##[1:3] ack;
    endproperty

    assert property (p_valid_handshake);

    property p_data_stable;
        @(posedge clk) disable iff (!rst_n)
        $stable(data) |-> ##1 $stable(data);
    endproperty

    assert property (p_data_stable);

    property p_state_check;
        @(posedge clk) disable iff (!rst_n)
        state == 4'h0 || state == 4'h1;
    endproperty

    assert property (p_state_check);

    // ============================================
    // 7. sequence with delay range
    // ============================================
    sequence s_data_stable;
        @(posedge clk) !rst_n or ($stable(data) [*3]);
    endsequence

    // s_valid_ready
    sequence s_valid_ready;
        valid && ready;
    endsequence

    // s_req_ack
    sequence s_req_ack;
        valid ##1 ready ##1 ack;
    endsequence

    // ============================================
    // 8. implication operators
    // ============================================
    assert property (@(posedge clk) disable iff (!rst_n)
        valid |=> ack);

    assert property (@(posedge clk) disable iff (!rst_n)
        valid |-> ##2 err == 1'b0);

    // ============================================
    // 9. complex expression
    // ============================================
    assert property (@(posedge clk) disable iff (!rst_n)
        (valid && ready && enable) |-> ##1 (count == buffer + 8'd1));

    // ============================================
    // 10. nested implication
    // ============================================
    assert property (@(posedge clk) disable iff (!rst_n)
        valid |-> (ready |-> ##1 ack));

    // ============================================
    // 11. throughout
    // ============================================
    assert property (@(posedge clk) disable iff (!rst_n)
        valid throughout ready [*3]);

    // ============================================
    // 12. within
    // ============================================
    assert property (@(posedge clk) disable iff (!rst_n)
        valid |-> (data != 8'h0) within ack);

    // ============================================
    // 13. first_match
    // ============================================
    assert property (@(posedge clk) disable iff (!rst_n)
        first_match(valid ##[1:$]) |-> ack);

    // ============================================
    // 14. eventually
    // ============================================
    assert property (@(posedge clk) disable iff (!rst_n)
        valid |-> s_eventually ack);

endmodule

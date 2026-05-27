// sva_generated_expected.sv
// 预期生成的 SVA 示例

module sva_expected (
  input logic clk,
  input logic rst_n,
  input logic valid,
  input logic ready,
  input logic [7:0] data
);

  // 从约束生成: c_simple { length inside {[1:64]}; data < length; }
  // → assert range
  property p_length_range;
    @(posedge clk) length inside {[1:64]};
  endproperty

  // 从条件生成: true_condition = rst_n && sel == 2'b00
  // → assert conditional path
  property p_cond_path;
    @(posedge clk) disable iff (!rst_n)
      (sel == 2'b00) |-> (out_if == a);
  endproperty

  // 从 FSM 生成: state == IDLE && cmd == LOAD -> next == EXEC
  property p_fsm_transition;
    @(posedge clk) disable iff (!rst_n)
      (state == IDLE && cmd == LOAD) |=> (next_state == EXEC);
  endproperty

  // 从信号关系生成: valid |-> ##1 ready
  property p_valid_ready;
    @(posedge clk) valid |-> ##1 ready;
  endproperty

endmodule

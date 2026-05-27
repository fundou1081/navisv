// ============================================================
// covergroup_class.sv
// CoverGroup 在 class 中的测试 + sample 条件
// ============================================================

package cg_class_pkg;

  class packet;
    rand bit [7:0] length;
    rand bit [7:0] data;
    rand bit [1:0] mode;

    constraint c_len {
      length inside {[1:64]};
    }
  endclass

  // ----------------------------------------------------------
  // 1. class 中的 covergroup
  // ----------------------------------------------------------
  class packet_cov;
    packet pkt;

    covergroup pkt_cg;
      option.per_instance = 1;

      cp_len: coverpoint pkt.length {
        bins zero = {0};
        bins low  = {[1:16]};
        bins mid  = {[17:48]};
        bins high = {[49:64]};
        illegal_bins overflow = {[65:255]};
      }

      cp_data: coverpoint pkt.data {
        bins lo = {[0:127]};
        bins hi = {[128:255]};
      }

      cp_mode: coverpoint pkt.mode;

      cx_len_mode: cross cp_len, cp_mode;
    endgroup

    function new();
      pkt_cg = new();
    endfunction
  endclass

  // ----------------------------------------------------------
  // 2. 无 sample 事件的 covergroup
  // ----------------------------------------------------------
  class cond_cov;
    bit [7:0] val;
    bit       en;

    covergroup cond_cg;
      option.per_instance = 1;

      cp_val: coverpoint val {
        bins low  = {[0:127]};
        bins high = {[128:255]};
      }
    endgroup
  endclass

  // ----------------------------------------------------------
  // 3. 多 covergroup 在同一 class
  // ----------------------------------------------------------
  class multi_cov;
    bit [7:0] a;
    bit [7:0] b;

    covergroup cg1;
      cp_a: coverpoint a {
        bins range = {[0:255]};
      }
    endgroup

    covergroup cg2;
      cp_b: coverpoint b {
        bins range = {[0:255]};
      }
      cp_a_ref: coverpoint a {
        bins lo = {[0:127]};
        bins hi = {[128:255]};
      }
    endgroup
  endclass

endpackage

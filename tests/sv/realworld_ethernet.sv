// ============================================================
// realworld_ethernet.sv
// 来源: ethernet_10ge_mac_SV_UVM_tb (开源以太网 UVM 项目)
// 提取 class/constraint 结构, 去掉 UVM 依赖
// ============================================================

package ethernet_pkg;

  // ----------------------------------------------------------
  // 基础 packet 类 (5 个 rand 变量, 3 个 constraint)
  // ----------------------------------------------------------
  class packet;
    rand bit [47:0]       mac_dst_addr;
    rand bit [47:0]       mac_src_addr;
    rand bit [15:0]       ether_type;
    rand bit [7:0]        payload [];
    rand bit [31:0]       ipg;

    rand bit              sop_mark;
    rand bit              eop_mark;

    constraint C_proper_sop_eop_marks {
      sop_mark == 1;
      eop_mark == 1;
    }

    constraint C_payload_size {
      payload.size() inside {[46:1500]};
    }

    constraint C_ipg {
      ipg inside {[10:50]};
    }
  endclass

  // ----------------------------------------------------------
  // 继承: packet_bringup (覆盖 + 新增约束)
  // ----------------------------------------------------------
  class packet_bringup extends packet;
    constraint C_bringup {
      mac_dst_addr      == 48'hAABB_CCDD_EEFF;
      mac_src_addr      == 48'h1122_3344_5566;
      ether_type        inside {16'h0800, 16'h0806, 16'h88DD};
      payload.size()    inside {[45:54]};
      ipg               == 10;
    }
  endclass

  // ----------------------------------------------------------
  // 继承: packet_oversized (覆盖 payload_size)
  // ----------------------------------------------------------
  class packet_oversized extends packet;
    constraint C_payload_size {
      payload.size() inside {[1501:9000]};
    }
  endclass

  // ----------------------------------------------------------
  // 继承: packet_undersized (覆盖 payload_size)
  // ----------------------------------------------------------
  class packet_undersized extends packet;
    constraint C_payload_size {
      payload.size() inside {[1:45]};
    }
  endclass

  // ----------------------------------------------------------
  // 继承: packet_small_ipg (覆盖 ipg)
  // ----------------------------------------------------------
  class packet_small_ipg extends packet;
    constraint C_ipg {
      ipg inside {[1:10]};
    }
  endclass

  // ----------------------------------------------------------
  // 继承: packet_zero_ipg (覆盖 ipg)
  // ----------------------------------------------------------
  class packet_zero_ipg extends packet;
    constraint C_ipg {
      ipg == 0;
    }
  endclass

  // ----------------------------------------------------------
  // wishbone_item 类
  // ----------------------------------------------------------
  typedef enum bit { READ=0, WRITE=1 } xtxn_mode;

  class wishbone_item;
    rand xtxn_mode    xtxn_n;
    rand bit[7:0]     xtxn_addr;
    rand bit[31:0]    xtxn_data;

    constraint C_xtxn_addr {
      xtxn_addr == 8'h00 ||
      xtxn_addr == 8'h08 ||
      xtxn_addr == 8'h0C ||
      xtxn_addr == 8'h10;
    }
  endclass

  // ----------------------------------------------------------
  // 组合: ethernet_env 包含 packet 和 wishbone_item
  // ----------------------------------------------------------
  class ethernet_env;
    rand packet       pkt;
    rand wishbone_item wb_item;
    rand bit [7:0]    ctrl_reg;

    constraint c_env_ctrl {
      ctrl_reg inside {8'h00, 8'h01, 8'h02};
    }

    constraint c_env_pkt_size {
      pkt.payload.size() inside {[64:1518]};
    }
  endclass

endpackage
